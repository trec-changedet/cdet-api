import json
import secrets

from annotated_types import doc
from certifi import where
from fastapi import FastAPI, Depends, HTTPException, Path, Query
from pydantic import BaseModel, ConfigDict
from typing import List, Annotated
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

# Pydantic definition for RAGTIME1 documents.
class DocumentSchema(BaseModel):
    id: str
    text: str
    url: str
    date: str
    day: str

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
    results: dict[str, List[QuestionResults]]
    extra: dict | None = None

class Run:
    def __init__(self, logfile: Path | None = None):
        self.metadata: dict[str, str] = {}
        self.topic_results: dict[str, TopicResults] = {}

        self.last_date_accessed: None | str = None
        self.logfile = logfile
        self._play_logfile()

    def _play_logfile(self):
        if not self.logfile.exists():
            return
        with open(self.logfile, 'r') as f:
            for line in f:
                message = json.loads(line)
                endpoint = message.get('endpoint')
                if endpoint == '/start_run':
                    self.metadata = message.get('metadata', {})
                elif endpoint == '/documents':
                     self.last_date_accessed = message.get('day')
                elif endpoint == '/retrieval':
                    topic = message.get('topic')
                    results = message.get('results')
                    metadata = message.get('metadata')
                    if topic and results:
                        self.topic_results[topic] = TopicResults(**results, extra=metadata)

    def save(self, output_path: Path):
        with open(output_path, 'w') as f:
            json.dump(self.metadata, f, indent=2)
            for topic in self.topic_results:
                json.dump(self.topic_results[topic].model_dump(), f, indent=2)

        
# Dependency to safely manage database connections per request
def get_db():
    try:
        db.connect(reuse_if_open=True)
        yield
    finally:
        if not db.is_closed():
            db.close()

@app.post('/start_run/{api_key}')
async def start_run(api_key: str, metadata: dict | None = None):
    if not valid_api_key(api_key):
        raise HTTPException(status_code=401, detail='Invalid API key')
    token = secrets.token_hex(23)
    # To do: store api_key, token pair
    log(f'{token}.log', {'endpoint': '/start_run', 'api_key': api_key, 'metadata': metadata})
    RunState.insert(token=token, metadata={'state': 'started', 'api_key': api_key}).execute()
    return {'token': token}

@app.get('/documents/{day}', response_model=List[DocumentSchema], dependencies=[Depends(get_db)])
def get_documents_by_day(
    day: Annotated[str, Path(pattern=r'^\d{4}-\d{2}-\d{2}$', 
                             description='The day to filter documents by, in YYYY-MM-DD format')],
    token: Annotated[str, Query(description='Authentication token obtained from /start_run', )]):
    '''
    Retrieve all documents for a specific day.
    Expected format for day parameter: YYYY-MM-DD
    '''
    if len(day) != 10:
        raise HTTPException(status_code=400, detail='Day must be in exactly YYYY-MM-DD format.')
    if not valid_token(token):
        raise HTTPException(status_code=401, detail='Invalid token')
    
    # Validate day: under this token, this day needs to follow the previous day or be the first day
    last_accessed_day = RunState.select(RunState.metadata['last_accessed_day']).where(RunState.token == token).scalar()
    last_seq_day = Day.select(Day.seq_day).where(Day.day == last_accessed_day).scalar() if last_accessed_day else -1
    this_seq_day = Day.select(Day.seq_day).where(Day.day == day).scalar()
    if this_seq_day != last_seq_day + 1:
        raise HTTPException(status_code=400, detail=f"Invalid day {day}. The last accessed day for this run is {last_accessed_day}, so the next day must be {Day.select(Day.day).where(Day.seq_day == last_seq_day + 1).scalar()}.")

    log(f'{token}.log', {'endpoint': '/documents', 'day': day})
    RunState.update(metadata={'last_accessed_day': day}).where(RunState.token == token).execute()

    # Query the SQLite database using Peewee
    query = Document.select().where(Document.day == day)
    
    # Evaluating the query via list() returns the Peewee instances, 
    # which FastAPI safely converts to JSON using the Pydantic DocumentSchema
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
    
    run = Run(pathlib.Path(settings.logdir) / f'{token}.log')

    for qr in results:
        if len(qr.doc_ranking) > 100:
            raise HTTPException(status_code=400, detail=f"Question {qr.qid} has {len(qr.doc_ranking)} retrieval results, exceeding the maximum of 100.")
        
        docs = (DocDay.select()
                .where(DocDay.docid.in_([hit.doc_id for hit in qr.doc_ranking]) & (DocDay.day != run.last_date_accessed))
                .exists())
        if docs:
            raise HTTPException(status_code=400, detail=f"Document {doc.docid} is from day {doc.day}, but the last accessed day for this run is {run.last_date_accessed}. Please ensure retrieval results are reported for the correct day.")

    log(f'{token}.log', {'endpoint': '/retrieval', 'topic': topic, 'results': [ foo.model_dump() for foo in results ], 'metadata': metadata})
    return {'status': 'success'}