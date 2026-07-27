import argparse
import json
import shutil
from contextlib import contextmanager
import tempfile
import os

import changedet_api
from changedet_api.api_client import ApiException
from changedet_api.models import RunMetadata, Hit, QuestionResults, DayResults
from pprint import pprint
import pyterrier as pt
import pandas as pd

from cdet_api import client

config = changedet_api.Configuration(
    host='http://127.0.0.1:8000'
)

run_def = RunMetadata(
    runtag='my-run', 
    description='Uses PyTerrier to index the documents on each day, search the docs using a BM25 search with the question, return the top 20 docs.',
    run_type='automatic',
    extern='No external data used.',
    models=[])

def build_index(docs, tmp_path):
    indexer = pt.IterDictIndexer(tmp_path, meta={'docno': 50}, text_attrs=['text'], overwrite=True)
    indexref = indexer.index(docs)
    return pt.IndexFactory.of(indexref)

@contextmanager
def self_cleaning_index(docs):
    tmp_dir = tempfile.mkdtemp()
    index = None

    try:
        index = build_index(docs, tmp_dir)
        yield index
    finally:
        if index is not None:
            try:
                index.close()
            except Exception as e:
                print(f"Error closing index: {e}")
        if os.path.exists(tmp_dir):
            shutil.rmtree(tmp_dir)

def convert_results(df):
    if df.empty:
        return {}
    grouped = df.groupby('qid')
    result = []
    for qid, group in grouped:
        query = group['query'].iloc[0]
        doc_ranking = list(zip(group['docno'], group['score']))
        doc_ranking = [ Hit(doc_id=hit[0], score=hit[1]) for hit in doc_ranking[:20] if hit[1] > 5 ]
        if len(doc_ranking) > 0:
            result.append(QuestionResults(qid=qid, question_text=query, question_rank=1, doc_ranking=doc_ranking))
    return result

def search(index, topic):
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
    ap.add_argument('topics',
                    help='Path to the topics file')
    args = ap.parse_args()

    with open(args.topics) as topics_file:
        topics = [json.loads(line) for line in topics_file]

    with changedet_api.ApiClient(config) as api_client:
        api_instance = changedet_api.DefaultApi(api_client)
        api_response = api_instance.start_run(api_key='abc123', run_metadata=run_def)
        token = api_response['token']
        shutil.rmtree('foo.index', ignore_errors=True)

        try:
            days = 0
            while True:
                days += 1
                if args.stop_after_n_days and days > args.stop_after_n_days:
                    break
                day_docs = [ { 'docno': doc.id, 'text': doc.text } for doc in api_instance.get_next_day(token) ]
                with self_cleaning_index(day_docs) as index:
                    for topic in topics:
                        results = search(index, topic)
                        result = client.retrieval(token=token, topic=topic['tid'], retrieval_results=DayResults(results=results))

        except ApiException:
            print("all done!")

    shutil.rmtree('foo.index', ignore_errors=True)
    runfile = api_instance.finalize_run(token, send=False)
    with open(f"{run_def.runtag}.json", 'w') as fp:
        print(runfile, file=fp)