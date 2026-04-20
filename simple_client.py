import argparse
import json
import shutil
import changedet_api
from changedet_api.api_client import ApiException
from changedet_api.models import Hit, QuestionResults
from pprint import pprint
import pyterrier as pt
import pandas as pd

config = changedet_api.Configuration(
    host='http://127.0.0.1:8000'
)

run_def = {
    'runtag': 'my-run',
    'description': 'Uses PyTerrier to index the documents on each day, search the docs using a BM25 search with the question, return the top 20 docs.'
}

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
        doc_ranking = [ Hit(doc_id=hit[0], score=hit[1]) for hit in doc_ranking[:5] ]
        result.append(QuestionResults(qid=qid, question_text=query, question_rank=1, doc_ranking=doc_ranking))
    return result

def search(index, topic):
    retriever = index.bm25() % 20
    df = pd.DataFrame([[q['qid'], q['question']] for q in topic['questions']], columns=['qid', 'query'])
    results = retriever(df)
    converted = convert_results(results)
    return converted

if __name__ == '__main__':
    ap = argparse.ArgumentParser('A simple CDet track API client')
    ap.add_argument('topics',
                    help='Path to the topics file')
    args = ap.parse_args()

    with open(args.topics) as topics_file:
        topics = [json.loads(line) for line in topics_file]

    with changedet_api.ApiClient(config) as api_client:
        api_instance = changedet_api.DefaultApi(api_client)
        api_response = api_instance.start_run(api_key='abc123', runtag=run_def['runtag'], request_body=run_def)
        token = api_response['token']

        try:
            while True:
                day_docs = [ { 'docno': doc.id, 'text': doc.text } for doc in api_instance.get_next_day(token) ]
                index = build_index(day_docs)
                for topic in topics:
                    results = search(index, topic)
                    result = api_instance.retrieval(token=token, topic=topic['tid'], body_retrieval_retrieval_post={'results': results})
                shutil.rmtree('foo.index')

        except ApiException:
            print("all done!")

    runfile = api_instance.finalize_run(token)
    with open(f"{run_def['runtag']}.json", 'r') as fp:
        fp.write(runfile)