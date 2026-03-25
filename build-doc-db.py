import argparse
import sqlite3
import json

if __name__ == "__main__":
    ap = argparse.ArgumentParser(description="Build a SQLite db for the RAGTIME corpus.")
    ap.add_argument('db', help="Path to the output SQLite database file.")
    ap.add_argument('corpus', help="Path to the RAGTIME corpus JSON file.")

    args = ap.parse_args()

    # Connect to the SQLite database (it will be created if it doesn't exist)
    conn = sqlite3.connect(args.db)
    c = conn.cursor()

    # Create the documents table
    c.execute('''CREATE TABLE IF NOT EXISTS documents
                 (id TEXT PRIMARY KEY, text TEXT, url TEXT, date TEXT, day TEXT)''')
    c.execute('''CREATE INDEX IF NOT EXISTS idx_day ON documents (day)''')

    # Load the RAGTIME corpus from the JSON file
    with open(args.corpus, 'r') as f:
        docs = [json.loads(line) for line in f]
        to_load = [(doc['id'], doc['text'], doc['url'], doc['date'], doc['date'].split('T')[0]) for doc in docs]

    try:
        c.executemany('INSERT OR REPLACE INTO documents (id, text, url, date, day) VALUES (?, ?, ?, ?, ?)', to_load)
        conn.commit()
    except sqlite3.Error as e:
        print(f"An error occurred: {e}")
        conn.rollback()
    finally:
        conn.close()