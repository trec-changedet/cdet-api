import json
import secrets

from fastapi import FastAPI, Depends, HTTPException, Path
from pydantic import BaseModel, ConfigDict
from typing import List, Annotated
from types import SimpleNamespace
import tomllib
import pathlib
from models import db, Document

app = FastAPI(title='Change Detection API')

settings_path = 'settings.toml'
with open(settings_path, 'rb') as f:
    settings = SimpleNamespace(**tomllib.load(f))

def log(logfile: str, message: object):
    with open(pathlib.Path(settings.logdir / logfile), 'a') as f:
        json.dump(message, f)

# placeholder for API key and token validation, to be implemented in the future
def valid_api_key(api_key: str) -> bool:
    return True

def valid_token(token: str) -> bool:
    return True

# Pydantic definition mapped for the Peewee model
class DocumentSchema(BaseModel):
    id: str
    text: str
    url: str
    date: str
    day: str

    # This configuration acts as the utility to map Peewee ORM models to Pydantic definitions
    # It tells Pydantic to read data as attributes (obj.id) rather than just dict lookups (obj['id'])
    model_config = ConfigDict(from_attributes=True)

class Hit(BaseModel):
    doc_id: str
    score: float

class RetrievalResults(BaseModel):
    qid: str
    question_rank: int
    question_text: str | None
    doc_ranking: List[Hit]
    extra: dict | None = None

class TopicResults(BaseModel):
    topic: str
    results: dict[str, List[RetrievalResults]]
    extra: dict | None = None


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
    return {'token': token}

@app.get('/documents/{day}', response_model=List[DocumentSchema], dependencies=[Depends(get_db)])
def get_documents_by_day(
    day: Annotated[str, Path(pattern=r'^\d{4}-\d{2}-\d{2}$', 
                             description='The day to filter documents by, in YYYY-MM-DD format')],
    token: str):
    '''
    Retrieve all documents for a specific day.
    Expected format for day parameter: YYYY-MM-DD
    '''
    if len(day) != 10:
        raise HTTPException(status_code=400, detail='Day must be in exactly YYYY-MM-DD format.')
    if not valid_token(token):
        raise HTTPException(status_code=401, detail='Invalid token')
    
    # Validate day: under this token, this day needs to follow the previous day or be the first day

    log(f'{token}.log', {'endpoint': '/documents/{day}', 'day': day})

    # Query the SQLite database using Peewee
    query = Document.select().where(Document.day == day)
    
    # Evaluating the query via list() returns the Peewee instances, 
    # which FastAPI safely converts to JSON using the Pydantic DocumentSchema
    return list(query)

@app.post('/retrieval')
async def retrieval(token: str, topic: str, results: RetrievalResults, metadata: dict | None = None):
    '''
    Report retrieval results for the current day.
    '''
    if not valid_token(token):
        raise HTTPException(status_code=401, detail='Invalid token')
    # Ensure that we are in some day (must have been preceeded by a /documents/{day} call) and that the topic is not empty
    
    log(f'{token}.log', {'endpoint': '/retrieval', 'topic': topic, 'results': results.model_dump(), 'metadata': metadata})
    
    return {'status': 'success'}