# CDET-API - A REST server for TREC Change Detection

This is a jig designed to make it easier to participate in and submit well-formed submissions to the TREC Change Detection track (trec.nist.gov, trec-changedet.github.io). It is a simple REST server written using FastAPI. You can automatically generate a client library for whatever implementation language you have, run this server locally, run your client against it, and submit the output to TREC.

### Installation

This is a fairly standard Python project. To set it up, create a virtual environment and install the packages in the `requirements.txt` file:
```bash
python3 -m venv .venv               # create the virtual environment
. .venv/bin/activate                # activate the environment
pip install -U pip                  # update pip, the Python package manager
pip install -r requirements.txt     # and install the dependencies
```

You need the English subset of the RAGTIME1 collection, available via HuggingFace at https://huggingface.co/datasets/trec-ragtime/ragtime1/blob/main/eng-docs.jsonl.

Next, compile the local SQLite database that is used to rapidly serve the documents for each day of the collection and maintain state for the server:
```bash
python -m scripts.build_doc_db /path/to/eng-docs.jsonl
```
This will create a database `docs.db` in the current directory.

### Running

In the server code cdet_api/server.py, there is a section that defines a set of permitted API keys:
```python
api_key_store = {
    'abc123': 'ian.soboroff@nist.gov'
}
```
If you plan to host this server beyond your local machine you should customize this and make sure that your users get individual, secure API keys. You can use Python's standard `secrets` library to generate keys:
```bash
$ python
Python 3.14.4 (main, Apr  7 2026, 13:13:20) [Clang 21.0.0 (clang-2100.0.123.102)] on darwin
Type "help", "copyright", "credits" or "license" for more information.
>>> import secrets
>>> secrets.token_hex()
'8b21a3504567032154b4763c227163e9c36617647a3f8b289a3b8a1072ace942'
>>> 
```

You can then start the API server, either in development mode:
```bash
fastapi dev cdet_api/server.py
```
or using uvicorn:
```bash
uvicorn cdet_api.server:app --host 0.0.0.0 --port 8000
```

More on deploying FastAPI apps can be found at https://fastapi.xiniushu.com/sv/deployment/manually/

Once the server is running, you can play with the API and see documentation at https://127.0.0.1:8000/docs. At that endpoint, you can access all the API endpoints through a generated web form. Be sure to use one of the API keys you defined in the server or the placeholder 'abc123' key.

### Generating a client library

You can automatically create an API library from the running server using any OpenAPI client generator library, see https://fastapi.xiniushu.com/sv/advanced/generate-clients/ and https://www.openapis.org/.

First, you need the API specification, which you can get from the running server:
```bash
curl -O http://127.0.0.1:8000/openapi.json
```

Here is an example of generating a Python library using `openapi-generator` (https://github.com/openapitools/openapi-generator), directly taking the API spec from the running server and applying a small amount of local configuration (`config.json`) to set the library name:
```bash
openapi-generator generate -i http://127.0.0.1:8000/openapi.json -g python -o sdks/python -c config.json
```
That generated API is in this repository in `sdks/python`, and there is a basic baseline TREC system in this repository, `simple_client.py`, that uses it:
```bash
# make sure the environment is active!
cd sdks/python
pip install .
cd ../..
fastapi dev cdet_api/server.py &
python simple_client.py test-topics.jsonl
```
That client will read the topics, run over the collection, generate results, and output a well-formed TREC run. `simple_client.py` uses PyTerrier to generate a BM25 ranking of each day's document set using the topic questions as queries.
