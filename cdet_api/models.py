from peewee import *
from playhouse.sqlite_ext import JSONField

# Initialize the SQLite database connection
db = SqliteDatabase('docs.db')

class Document(Model):
    id = CharField(primary_key=True)
    text = TextField()
    url = CharField()
    date = CharField()
    
    # Extracting day from date, setting an index for fast lookups in the REST API
    day = CharField(index=True)

    class Meta:
        database = db
        table_name = 'documents'

class DocDay(Model):
    docid = CharField(primary_key=True, index=True)
    day = CharField()

    class Meta:
        database = db
        table_name = 'doc_days'

class Day(Model):
    day = CharField(primary_key=True)
    seq_day = IntegerField()

    class Meta:
        database = db
        table_name = 'days'

class RunState(Model):
    token = CharField(primary_key=True)
    metadata = JSONField()

    class Meta:
        database = db
        table_name = 'run_states'