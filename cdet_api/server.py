import io
import json
import secrets
import time

from annotated_types import doc
from certifi import where
from fastapi import FastAPI, Depends, HTTPException, Path, Query
from fastapi.responses import StreamingResponse
from fastapi.routing import APIRoute
from pydantic import BaseModel, ConfigDict, Field, RootModel, StringConstraints
from typing import List, Annotated, Tuple
from types import SimpleNamespace
import tomllib
import pathlib
from cdet_api.models import Day, DocDay, db, Document, RunState

app = FastAPI(title='Change Detection API')

# Keep settings in a TOML file
settings_path = 'settings.toml'
with open(settings_path, 'rb') as f:
    settings = SimpleNamespace(**tomllib.load(f))

# Ensure tables exist in the database
db.connect()
db.create_tables([Document, DocDay, RunState], safe=True)
db.close()

# The data storage mechanism for API use on the server is
# an append-only log file of JSON lines for each token.
# When a run is complete, the API plays the log file to
# create the final output and sends it to the user.
def log(logfile: str, message: object):
    with open(pathlib.Path(settings.logdir) / logfile, 'a') as f:
        print(json.dumps(message), file=f)

# placeholder for API key and token validation, to be implemented in the future
api_key_store = {
    'abc123': 'ian.soboroff@nist.gov'
}

def valid_api_key(api_key: str) -> bool:
    return api_key in api_key_store

def valid_token(token: str) -> bool:
    return (pathlib.Path(settings.logdir) / f'{token}.log').exists()

def update_run_state(token: str, **kwargs):
    RunState.update(metadata={**kwargs, 'timestamp': time.time()}).where(RunState.token == token).execute()

def clean_run_states(since=2 * 24 * 60 * 60):
    # Remove run states that have not been updated in the last 2 days
    cutoff_time = time.time() - since
    old_runs = RunState.select().where(RunState.metadata['timestamp'] < cutoff_time)
    for run in old_runs:
        (pathlib.Path(settings.logdir) / f'{run.token}.log').unlink(missing_ok=True)
        run.delete_instance()

# Pydantic definition for RAGTIME1 documents.

type DayString = Annotated[str, StringConstraints(pattern=r'^\d{4}-\d{2}-\d{2}$', min_length=10, max_length=10)]
class DocumentSchema(BaseModel):
    id: str
    text: str
    url: str
    date: str
    day: DayString

    # This configuration acts as the utility to map Peewee ORM models to Pydantic definitions
    # It tells Pydantic to read data as attributes (obj.id) rather than just dict lookups (obj['id'])
    model_config = ConfigDict(from_attributes=True)

# A search hit
class Hit(BaseModel):
    doc_id: str
    score: float

class QuestionResults(BaseModel):
    qid: str
    question_rank: int
    question_text: str | None
    doc_ranking: List[Hit]
    extra: dict | None = None

class TopicResults(BaseModel):
    topic: str
    results: dict[DayString, List[QuestionResults]]
    extra: dict | None = None

class RunMetadata(BaseModel):
    runtag: Annotated[str, Field(max_length=20)]
    model_config = ConfigDict(extra='allow')

Run = RootModel[Tuple[RunMetadata, List[TopicResults]]]

# Dependency to safely manage database connections per request
def get_db():
    try:
        db.connect(reuse_if_open=True)
        yield
    finally:
        if not db.is_closed():
            db.close()

@app.post('/start_run/{api_key}', dependencies=[Depends(get_db)])
async def start_run(api_key: str, runtag: str, metadata: dict | None = None):
    clean_run_states()  # Clean up old run states on each new run start
    if not valid_api_key(api_key):
        raise HTTPException(status_code=401, detail='Invalid API key')
    token = secrets.token_hex(23)
    # To do: store api_key, token pair
    log(f'{token}.log', {'endpoint': '/start_run', 'api_key': api_key, 'runtag': runtag, 'metadata': metadata})
    RunState.insert(token=token, metadata={'state': 'started', 'api_key': api_key, 'timestamp': time.time()}).execute()
    return {'token': token}

@app.get('/next_day', response_model=List[DocumentSchema], dependencies=[Depends(get_db)])
async def get_next_day(token: Annotated[str, Query(description='Authentication token obtained from /start_run', )]):
    '''
    Retrieve documents for the next day in the sequence.
    This endpoint is an alternative to /documents/{day} that automatically determines the next day based on the last accessed day for this token.
    '''
    if not valid_token(token):
        raise HTTPException(status_code=401, detail='Invalid token')
    
    last_accessed_day = RunState.select(RunState.metadata['last_accessed_day']).where(RunState.token == token).scalar()
    if last_accessed_day is None:
        # If no day has been accessed yet, start with the first day in the database
        next_day = Day.select(Day.day).where(Day.seq_day == 0).scalar()
    else:
        last_seq_day = Day.select(Day.seq_day).where(Day.day == last_accessed_day).scalar()
        next_day = Day.select(Day.day).where(Day.seq_day == last_seq_day + 1).scalar()

    if next_day is None:
        raise HTTPException(status_code=404, detail='No more days available')

    log(f'{token}.log', {'endpoint': '/next_day', 'day': next_day})
    update_run_state(token, last_accessed_day=next_day)

    query = Document.select().where(Document.day == next_day)
    return list(query)

@app.post('/retrieval', dependencies=[Depends(get_db)])
async def retrieval(token: str, 
                    topic: str, 
                    results: List[QuestionResults], 
                    metadata: dict | None = None):
    '''
    Report retrieval results for the current day.
    '''
    if not valid_token(token):
        raise HTTPException(status_code=401, detail='Invalid token')
    # Ensure that we are in some day (must have been preceeded by a /documents/{day} call) and that the topic is not empty
    
    today = RunState.select(RunState.metadata['last_accessed_day']).where(RunState.token == token).scalar()
    if today is None:
        raise HTTPException(status_code=400, detail='No day has been accessed yet for this token. Please call /next_day before reporting retrieval results.')
    if not topic:
        raise HTTPException(status_code=400, detail='Topic cannot be empty.')

    for qr in results:
        if len(qr.doc_ranking) > 100:
            raise HTTPException(status_code=400, detail=f"Question {qr.qid} has {len(qr.doc_ranking)} retrieval results, exceeding the maximum of 100.")
        
        docs = (DocDay.select()
                .where(DocDay.docid.in_([hit.doc_id for hit in qr.doc_ranking]) & (DocDay.day != today))
                .exists())
        if docs:
            raise HTTPException(status_code=400, detail=f"Document {doc.docid} is from day {doc.day}, but the last accessed day for this run is {today}. Please ensure retrieval results are reported for the correct day.")

    log(f'{token}.log', {'endpoint': '/retrieval', 'topic': topic, 'results': [ foo.model_dump() for foo in results ], 'retrieval_extra': metadata})
    return {'status': 'success'}

@app.get('/finalize_run', response_model=Run, dependencies=[Depends(get_db)])
async def finalize_run(token: str):
    if not valid_token(token):
        raise HTTPException(status_code=401, detail='Invalid token')
    
    results_per_topic = {}
    metadata_block = None
    errors = []
    with open(pathlib.Path(settings.logdir) / f'{token}.log', 'r') as f:
        current_day = None
        for line in f:
            le = json.loads(line)

            if le['endpoint'] == '/start_run':
                metadata_block = {
                    'runtag': le.get('runtag', 'my_run'),
                    **(le.get('metadata', None))
                }

            elif le['endpoint'] == '/next_day':
                current_day = le['day']

            elif le['endpoint'] == '/retrieval':
                topic = le['topic']
                if topic not in results_per_topic:
                    results_per_topic[topic] = {
                        'topic': topic,
                        'extra': le.get('metadata', None),
                        'results': {}
                    }
                results_per_topic[topic]['results'][current_day] = le['results']

    output = [metadata_block]
    for topic in results_per_topic:
        output.append(results_per_topic[topic])

    if len(errors) > 0:
        output.append({ 'errors': errors })

    log(f'{token}.log', {'endpoint': '/finalize_run'})
    update_run_state(token, state='finalized')
    RunState.delete().where(RunState.token == token).execute()
    return output

def use_route_names_as_operation_ids(app: FastAPI) -> None:
    """
    Simplify operation IDs so that generated API clients have simpler function
    names.

    Should be called only after all routes have been added.
    """
    for route in app.routes:
        if isinstance(route, APIRoute):
            route.operation_id = route.name  # in this case, 'read_items'


use_route_names_as_operation_ids(app)