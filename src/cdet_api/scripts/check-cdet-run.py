#!/usr/bin/env python3

import json
import sys
import traceback
from pathlib import Path
from pydantic import ValidationError

from cdet_api.types import RunMetadata, TopicResults, DayResults, QuestionResults, Hit

class Errlog():
    '''This is meant to be used in a context manager, for example:
    with Errlog(foo) as log:
        ...
    If not, be sure to call .close() when done.
    '''
    def __init__(self, runfile, max_errors=50):
        self.filename = runfile + '.errlog'
        self.fp = open(self.filename, 'w')
        self.error_count = 0
        self.max_errors = max_errors

    def __enter__(self):
        return self

    def close(self):
        if self.error_count == 0:
            print('No errors', file=self.fp)
        self.fp.close()

    def __exit__(self, exc_type, exc_value, tb):
        self.close()

    def error(self, line, msg):
        err_msg = f'ERROR Line {line}: {msg}'
        print(err_msg, file=sys.stderr)
        print(err_msg, file=self.fp)
        self.error_count += 1
        if self.error_count > self.max_errors:
            raise ValueError('Too many errors, stopping check.')

    def warn(self, line, msg):
        warn_msg = f'WARNING Line {line}: {msg}'
        print(warn_msg, file=sys.stderr)
        print(warn_msg, file=self.fp)


def format_pydantic_error(error):
    # Simplify and format Pydantic validation location paths nicely
    loc = error.get('loc', [])
    loc_path = " -> ".join(str(x) for x in loc if x != 'results')
    msg = error.get('msg', 'Unknown validation error')
    if loc_path:
        return f"Structure error at '{loc_path}': {msg}"
    return msg


def load_expected_dates(dates_file_path):
    dates_path = Path(dates_file_path)
    if not dates_path.exists():
        raise FileNotFoundError(f"Expected dates file '{dates_file_path}' not found")
    with open(dates_path, "r", encoding="utf-8") as f:
        return {line.strip() for line in f if line.strip()}


def check_cdet_run(args, log):
    expected_dates = load_expected_dates(args.dates)
    seen_topics = set()
    seen_metadata = False

    runfile_path = Path(args.runfile)
    if not runfile_path.exists():
        raise FileNotFoundError(f"Run file '{args.runfile}' not found")

    with open(runfile_path, 'r', encoding='utf-8') as fp:
        for line_num, line_raw in enumerate(fp, start=1):
            line = line_raw.strip()
            if not line:
                continue

            try:
                data = json.loads(line)
            except json.JSONDecodeError as jde:
                log.error(line_num, f"Invalid JSON format: {jde}")
                continue

            # First line MUST be RunMetadata
            if line_num == 1:
                if 'runtag' not in data:
                    log.error(line_num, "First line of run file must be run metadata containing 'runtag'")
                    return # Critical error: cannot verify runtag or metadata

                try:
                    meta = RunMetadata.model_validate(data)
                    seen_metadata = True
                except ValidationError as ve:
                    for error in ve.errors():
                        log.error(line_num, f"Metadata validation error: {format_pydantic_error(error)}")
                    return # Critical error: metadata cannot be parsed

                if meta.runtag != args.runtag:
                    log.error(line_num, f"Run tag inconsistent (file has '{meta.runtag}' but expected '{args.runtag}')")
                    return # Critical error: runtag mismatch

                continue

            # Subsequent lines must not be Metadata
            if 'runtag' in data:
                log.error(line_num, "Run metadata structure found after the first line")
                continue

            # Preprocess results structure to match Pydantic schema
            # Pydantic TopicResults.results is dict[DayString, DayResults].
            # DayResults contains results: list[QuestionResults].
            # In serialized files, results mapped to days are directly lists of QuestionResults.
            # We map list [QuestionResults] into a dictionary {"results": list} to correctly validate.
            if 'results' in data and isinstance(data['results'], dict):
                for day, day_val in data['results'].items():
                    if isinstance(day_val, list):
                        data['results'][day] = {'results': day_val}

            # Validate against TopicResults Pydantic schema
            try:
                topic_res = TopicResults.model_validate(data)
            except ValidationError as ve:
                for error in ve.errors():
                    log.error(line_num, f"Topic validation error: {format_pydantic_error(error)}")
                continue

            # Topic uniqueness check
            if topic_res.topic in seen_topics:
                log.error(line_num, f"Topic '{topic_res.topic}' is defined more than once in the file")
            seen_topics.add(topic_res.topic)

            # Date completeness checks
            topic_days = set(topic_res.results.keys())
            missing_days = expected_dates - topic_days
            if missing_days:
                sample_missing = sorted(list(missing_days))[:5]
                log.error(line_num, f"Topic '{topic_res.topic}' is missing output for {len(missing_days)} expected days (e.g. {', '.join(sample_missing)})")

            extra_days = topic_days - expected_dates
            if extra_days:
                sample_extra = sorted(list(extra_days))[:5]
                log.error(line_num, f"Topic '{topic_res.topic}' has {len(extra_days)} unexpected days not present in the dates file (e.g. {', '.join(sample_extra)})")

            # Check daily document and question rankings
            for day, day_res in topic_res.results.items():
                for q_res in day_res.results:
                    # Enforce max 100 documents per question per day
                    num_docs = len(q_res.doc_ranking)
                    if num_docs > 100:
                        log.error(line_num, f"Question '{q_res.qid}' on day '{day}' has {num_docs} retrieval results, exceeding the limit of 100")

                    # Check for duplicate document IDs in retrieval results
                    seen_docs = set()
                    for hit in q_res.doc_ranking:
                        if hit.doc_id in seen_docs:
                            log.error(line_num, f"Document ID '{hit.doc_id}' is retrieved more than once for question '{q_res.qid}' on day '{day}'")
                        seen_docs.add(hit.doc_id)

    if not seen_metadata:
        log.error(0, "No run metadata was found in the file")
    if not seen_topics:
        log.error(0, "No topic results were found in the file")


if __name__ == '__main__':
    import argparse

    ap = argparse.ArgumentParser(
        description='Checker for Change Detection (CDet) JSONL runs',
        formatter_class=argparse.ArgumentDefaultsHelpFormatter
    )
    ap.add_argument('-d', '--dates', required=True, help='Path to the expected dates file (one YYYY-MM-DD per line)')
    ap.add_argument('runtag', help='Run identifier/tag to verify (must match metadata in file)')
    ap.add_argument('runfile', help='Path to the JSONL run file to check')

    args = ap.parse_args()

    with Errlog(args.runfile) as log:
        try:
            check_cdet_run(args, log)
        except ValueError as ve:
            if "Too many errors" in str(ve):
                print(f"Checking stopped: {ve}", file=sys.stderr)
            else:
                log.error(-1, f"ValueError: {ve}")
        except Exception as e:
            log.error(-1, f"Unexpected error during run checking: {e}")
            traceback.print_exc()
            sys.exit(255)

        if log.error_count > 0:
            print(f"Validation failed with {log.error_count} errors. Check report written to {log.filename}", file=sys.stderr)
            sys.exit(255)
        else:
            print(f"Validation successful! No errors found. Log file: {log.filename}", file=sys.stderr)
            sys.exit(0)
