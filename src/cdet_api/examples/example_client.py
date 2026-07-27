import argparse
import json
import os
import shutil
from contextlib import contextmanager
import tempfile
from pprint import pprint

from cdet_api.client import CDetClient, NoMoreDaysException
from cdet_api.types import *
import pyterrier as pt
import pandas as pd

run_def = RunMetadata(
    runtag='my-run', 
    description='Uses PyTerrier to index the documents on each day, search the docs using a BM25 search with the question, return the top 20 docs.',
    run_type='automatic',
    extern='No external data used.',
    models=[])

def build_index(docs, index_path):
    indexer = pt.IterDictIndexer(index_path, meta={'docno': 50}, text_attrs=['text'], overwrite=True)
    indexref = indexer.index(docs)
    return pt.IndexFactory.of(indexref)

@contextmanager
def self_cleaning_index(docs):
    # Use tempfile to guarantee a unique path for every loop iteration
    # This prevents Terrier's internal cache from confusing new indices with old ones
    tmp_dir = tempfile.mkdtemp()
    index = None

    try:
        index = build_index(docs, tmp_dir)
        yield index
    finally:
        # 1. Close the actual Java object holding the file descriptors
        if index is not None:
            try:
                index.close()
            except Exception as e:
                print(f"Error closing index: {e}")

        # 2. Safely delete the physical files from disk
        if os.path.exists(tmp_dir):
            shutil.rmtree(tmp_dir)

def convert_results(df) -> List[QuestionResults]:
    if df.empty:
        return []
    grouped = df.groupby('qid')
    result = []
    for qid, group in grouped:
        query = group['query'].iloc[0]
        doc_ranking = list(zip(group['docno'], group['score']))
        doc_ranking = [ Hit(doc_id=hit[0], score=hit[1]) for hit in doc_ranking[:20] if hit[1] > 5 ]
        if len(doc_ranking) > 0:
            result.append(QuestionResults(qid=qid, question_text=query, question_rank=1, doc_ranking=doc_ranking))
    return result

def search(index, topic) -> List[QuestionResults]:
    retriever = pt.terrier.Retriever(index, wmodel='BM25', num_results=20)
    df = pd.DataFrame([[q['qid'], q['question']] for q in topic['questions']], columns=['qid', 'query'])
    results = retriever(df)
    converted = convert_results(results)
    return converted

if __name__ == '__main__':
    ap = argparse.ArgumentParser('A simple CDet track API client')
    ap.add_argument('-d', '--stop_after_n_days',
                    help='Stop the run after N days',
                    type=int)
    ap.add_argument('-u', '--base_url',
                    help='URL of REST API',
                    default='http://127.0.0.1:8000')
    ap.add_argument('topics',
                    help='Path to the topics file')
    args = ap.parse_args()

    with open(args.topics) as topics_file:
        topics = [json.loads(line) for line in topics_file]

    client = CDetClient(base_url=args.base_url)

    token = client.start_run(api_key='abc123', metadata=run_def)

    try:
        days = 0
        while True:
            days += 1
            if args.stop_after_n_days and days > args.stop_after_n_days:
                break
            day_docs = [ { 'docno': doc.id, 'text': doc.text } for doc in client.next_day(token) ]
            with self_cleaning_index(day_docs) as index:
                for topic in topics:
                    results = search(index, topic)
                    result = client.retrieval(token=token, topic=topic['tid'], retrieval_results=DayResults(results=results))

    except NoMoreDaysException:
        print("all done!")

    runfile = client.finalize_run(token, output_filename=f'{run_def.runtag}.json')
