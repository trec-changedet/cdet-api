from typing import Annotated, List, Union
from pydantic import BaseModel, ConfigDict, Field, StringConstraints, TypeAdapter

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

class DayResults(BaseModel):
    results: list[QuestionResults]
    extra: dict | None = None

class TopicResults(BaseModel):
    topic: str
    results: dict[DayString, DayResults]
    extra: dict | None = None

class RunMetadata(BaseModel):
    runtag: str = Field(
        title='Runtag',
        description="Run identifier. Must be 20 characters or less, contain only numbers, letters, periods, hyphens, and underscores, and not begin with a period.",
        max_length=20,
        min_length=1,
        pattern=r'^[a-zA-Z0-9_-][a-zA-Z0-9_.-]{1,20}$',
        examples=['my_run', 'NISTrun1']
    )
    description: str = Field(
        title='Description',
        description='Provide a description of your run that briefly explains your approach to the task.',
        examples=['Provide a description of your run that briefly explains your approach to the task.']
    )
    models: list[str] = Field(
        title='Models',
        description='Give names or URLs of LLMs used in this run. The names should be enough to allow others to reproduce your run.',
        examples=[['gemini-3.1-pro-preview', 'meta/llama-4-maverick-17b-128e-instruct-maas', 'claude-sonnet-4-6']]
    )

Run = list[Union[RunMetadata, TopicResults, dict[str,str]]]
Run_adapter = TypeAdapter(Run)

