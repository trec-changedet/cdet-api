import peewee

# Initialize the SQLite database connection
db = peewee.SqliteDatabase('docs.db')

class Document(peewee.Model):
    id = peewee.CharField(primary_key=True)
    text = peewee.TextField()
    url = peewee.CharField()
    date = peewee.CharField()
    
    # Extracting day from date, setting an index for fast lookups in the REST API
    day = peewee.CharField(index=True)

    class Meta:
        database = db
        table_name = 'documents'