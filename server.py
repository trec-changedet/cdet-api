import sqlite3
import argparse
from fastapi import FastAPI
from pydantic import BaseModel

ap = argparse.ArgumentParser(description="Start a Change Detection track API server.")
ap.add_argument('--db', default='docs.db', help="Path to the SQLite database file")

args = ap.parse_args()

app = FastAPI()
conn = sqlite3.connect(args.db)
c = conn.cursor()

class Document(BaseModel):
    id: str
    text: str
    url: str
    date: str

class DocumentBatch(BaseModel):
    documents: list[Document]

@app.get('/')
async def root():
    '''
    Return general information about the API server.
    '''
    return {'identity': 'cdet-api/server',
            'version': '0.1.0'}

@app.get('/inbox/{date}')
async def get_inbox(date: str) -> DocumentBatch:
    '''
    Retrieve all the documents for a given date.

    **TO DO**: when we can track users, make sure they are stepping through
    the days in order.
    **TO DO**: add validation for the date format (should be YYYY-MM-DD).
    '''
    c.execute('SELECT id, text, url, date FROM documents WHERE day = ?', (date,))
    rows = c.fetchall()
    documents = [Document(id=row[0], text=row[1], url=row[2], date=row[3]) for row in rows]
    return DocumentBatch(documents=documents)

@app.post('/start-run')
async def start_run(api_key: str, runtag: str):
    '''
    Start a new run for a user. This will create a new entry in the runs table
    and return the run ID.

    **TO DO**: implement API key authentication and user management.
    **TO DO**: this starts a session where interactions on this run are stored
    and then sent to the user when the run is declared complete. If there is a
    gap of more than 24 hours between interactions, the session should be closed and
    the run infomation deleted. This is to prevent the database from filling up with 
    old runs that are never completed.
    '''
    # For now, we'll just return a dummy token.
    return {'runtag': runtag,
            'token': 'dummy-token'}

# this needs to grow to encompass the results format
class RunResults(BaseModel):
    runtag: str
    token: str
    results: dict

@app.post('/complete-run')
async def complete_run(token: str) -> RunResults:
    '''
    Complete a run for a user. This will mark the run as complete in the database
    and return the results of the run.

    **TO DO**: implement API key authentication and user management.
    **TO DO**: implement logic to retrieve the results of the run from the database.
    '''
    # For now, we'll just return a dummy result.
    # 1. roll up the data for this run
    # 2. clear out the token
    # 3. return the results
    return RunResults(runtag='dummy-runtag', token=token, results={'dummy': 'result'})