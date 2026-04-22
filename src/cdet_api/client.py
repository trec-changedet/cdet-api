from pydantic import ValidationError

from cdet_api.types import *
import requests

# This is a basic but complete API to the FastAPI server


class NoMoreDaysException(Exception):
    '''This exception is thrown when a call to the /next_day endpoint returns 404, indicating no more days.'''
    pass

class CDetClient:
    def __init__(self, 
                 base_url='http://127.0.0.1:8000',
                 timeout=30,
                 ):
        self.base_url = base_url
        self.timeout = timeout
        self.session = requests.Session()
        self.session.headers.update({"Content-Type": "application/json"})

    def start_run(self, api_key: str, metadata: RunMetadata) -> str:
        url = f'{self.base_url}/start_run/{api_key}'
        payload = metadata.model_dump()
        try:
            response = self.session.post(url, json=payload, timeout=self.timeout)
            response.raise_for_status()
            data = response.json()
            return data['token']
        except requests.RequestException as e:
            print(f'/start_run Request error: {e}')
    
    def next_day(self, token: str) -> List[DocumentSchema]:
        url = f'{self.base_url}/next_day'
        params = { 'token': token }
        result_adapter = TypeAdapter(list[DocumentSchema])
        try:
            response = self.session.get(url, params=params, timeout=self.timeout)
            response.raise_for_status()
            docs = result_adapter.validate_python(response.json())
            return docs
        except ValidationError as ve:
            print(f'/next_day Validation error: {ve}')
        except requests.RequestException as e:
            if response.status_code == 404:
                raise NoMoreDaysException()
            print(f'/next_day Request error: {e}')

    def retrieval(self, token: str, topic: str, retrieval_results: DayResults):
        url = f'{self.base_url}/retrieval'
        params = {'token': token, 'topic': topic}
        payload = retrieval_results.model_dump()
        try:
            response = self.session.post(url, params=params, json=payload, timeout=self.timeout)
            response.raise_for_status()
        except requests.RequestException as e:
            print(f'/retrieval Request error: {e}')

    def finalize_run(self, token: str, output_filename: str) -> bytes | dict:
        url = f'{self.base_url}/finalize_run'
        params = { 'token': token, 'send': True }
        try:
            response = self.session.get(url, params=params, timeout=self.timeout)
            response.raise_for_status()
            resp_type = response.headers.get('content-type')
            if resp_type == 'application/json':
                return response.json()
            else:
                with open(output_filename, 'wb') as fp:
                    for chunk in response.iter_content(chunk_size=131072):
                        fp.write(chunk)
        except requests.RequestException as e:
            print(f'/finalize_run Request error: {e}')
