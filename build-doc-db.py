import json
import sys
from models import db, Document
from tqdm import tqdm

def load_jsonl_to_sqlite(file_path: str):
    """
    Loads a JSON lines file into the SQLite database.
    Each line is expected to be a JSON object with: id, text, url, date.
    """
    # Connect to DB and ensure the table exists
    db.connect()
    db.create_tables([Document])

    batch_size = 1000
    batch = []

    with open(file_path, 'r', encoding='utf-8') as f:
        for line_number, line in tqdm(enumerate(f, start=1), desc="Loading documents"):
            try:
                data = json.loads(line.strip())
                
                # Extract the YYYY-MM-DD portion. 
                # Assuming 'date' is ISO 8601 formatted or at least starts with the date.
                raw_date = data.get('date', '')
                day = raw_date[:10] if len(raw_date) >= 10 else raw_date

                batch.append({
                    'id': data.get('id'),
                    'text': data.get('text'),
                    'url': data.get('url'),
                    'date': raw_date,
                    'day': day
                })

                # Perform a bulk insert every 1000 rows for performance
                if len(batch) >= batch_size:
                    with db.atomic():
                        Document.insert_many(batch).execute()
                    batch = []
                    
            except json.JSONDecodeError:
                print(f"Skipping invalid JSON on line {line_number}")
            except Exception as e:
                print(f"Error on line {line_number}: {e}")

        # Insert any remaining documents
        if batch:
            with db.atomic():
                Document.insert_many(batch).execute()
            print(f"Finished loading a total of {line_number} documents.")

    db.close()

if __name__ == '__main__':
    if len(sys.argv) < 2:
        print("Usage: python loader.py <path_to_jsonl_file.jsonl>")
        sys.exit(1)
    
    load_jsonl_to_sqlite(sys.argv[1])