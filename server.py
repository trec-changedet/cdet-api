from fastapi import FastAPI, Depends, HTTPException
from pydantic import BaseModel, ConfigDict
from typing import List
from models import db, Document

app = FastAPI(title="Change Detection API")

# Pydantic definition mapped for the Peewee model
class DocumentSchema(BaseModel):
    id: str
    text: str
    url: str
    date: str
    day: str

    # This configuration acts as the utility to map Peewee ORM models to Pydantic definitions
    # It tells Pydantic to read data as attributes (obj.id) rather than just dict lookups (obj["id"])
    model_config = ConfigDict(from_attributes=True)

# Dependency to safely manage database connections per request
def get_db():
    try:
        db.connect(reuse_if_open=True)
        yield
    finally:
        if not db.is_closed():
            db.close()

@app.get("/documents/{day}", response_model=List[DocumentSchema], dependencies=[Depends(get_db)])
def get_documents_by_day(
    day: Annotated[str, Path(pattern=r"^\d{4}-\d{2}-\d{2}$", 
                             description="The day to filter documents by, in YYYY-MM-DD format")]):
    """
    Retrieve all documents for a specific day.
    Expected format for day parameter: YYYY-MM-DD
    """
    if len(day) != 10:
        raise HTTPException(status_code=400, detail="Day must be in exactly YYYY-MM-DD format.")

    # Query the SQLite database using Peewee
    query = Document.select().where(Document.day == day)
    
    # Evaluating the query via list() returns the Peewee instances, 
    # which FastAPI safely converts to JSON using the Pydantic DocumentSchema
    return list(query)