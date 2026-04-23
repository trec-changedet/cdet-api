import argparse
import json
import shutil
from pprint import pprint
from cdet_api.client import CDetClient, NoMoreDaysException
from cdet_api.types import *
import pyterrier as pt
import pandas as pd

run_def = RunMetadata(
    runtag='my-run', 
    description='Uses PyTerrier to index the documents on each day, search the docs using a BM25 search with the question, return the top 20 docs.',
    models=[])

def build_index(docs):
    index = pt.terrier.TerrierIndex('foo.index', memory=True)
    indexer = index.indexer(meta={'docno': 50}, text_attrs=['text'])
    indexer.index(docs)
    return index

def convert_results(df):
    if df.empty:
        return {}
    grouped = df.groupby('qid')
    result = []
    for qid, group in grouped:
        query = group['query'].iloc[0]
        doc_ranking = list(zip(group['docno'], group['score']))
        doc_ranking = [ Hit(doc_id=hit[0], score=hit[1]) for hit in doc_ranking[:20] ]
        result.append(QuestionResults(qid=qid, question_text=query, question_rank=1, doc_ranking=doc_ranking))
    return result

def search(index, topic):
    retriever = index.bm25() % 20 # this doesn't seem to be working to limit the results list
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
    shutil.rmtree('foo.index', ignore_errors=True)

    try:
        days = 0
        while True:
            days += 1
            if args.stop_after_n_days and days > args.stop_after_n_days:
                break
            day_docs = [ { 'docno': doc.id, 'text': doc.text } for doc in client.next_day(token) ]
            index = build_index(day_docs)
            for topic in topics:
                results = search(index, topic)
                result = client.retrieval(token=token, topic=topic['tid'], retrieval_results=DayResults(results=results))
            shutil.rmtree('foo.index')

    except NoMoreDaysException:
        print("all done!")

    shutil.rmtree('foo.index', ignore_errors=True)
    runfile = client.finalize_run(token, output_filename=f'{run_def.runtag}.json')
