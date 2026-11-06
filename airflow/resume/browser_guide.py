"""Open this computer's pending Airflow material forms once per intake."""
import json
import msvcrt
import os
from pathlib import Path
import re
import sys
import time
import urllib.error
import urllib.request
import webbrowser

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / 'dags'))
from resume_flow.storage import write_json

BASE = 'http://localhost:8765'
WORKSPACE = Path(__file__).resolve().parents[1] / 'resume_workspace'


def run():
    WORKSPACE.mkdir(parents=True, exist_ok=True)
    with (WORKSPACE / 'browser-guide.lock').open('a+b') as lock:
        lock.seek(0)
        try:
            msvcrt.locking(lock.fileno(), msvcrt.LK_NBLCK, 1)
        except OSError:
            return
        token = ''

        def request(path, payload=None):
            headers = {'X-Resume-Portal': '1', 'Authorization': 'Bearer ' + token,
                       'Content-Type': 'application/json'}
            body = None if payload is None else json.dumps(payload).encode()
            with urllib.request.urlopen(urllib.request.Request(BASE + path, body, headers), timeout=5) as response:
                return json.load(response)

        while True:
            try:
                if not token:
                    token = request('/api/session')['token']
                for entry in request('/api/intakes')['intakes']:
                    if entry.get('opened') or not re.fullmatch(r'[0-9a-f]{32}', entry['id']):
                        continue
                    if webbrowser.open(BASE + '/?intake_id=' + entry['id']):
                        request('/api/intake-opened', {'intake_id': entry['id']})
                write_json(WORKSPACE / 'browser-guide.json', {'pid': os.getpid(), 'heartbeat': time.time()})
            except (OSError, ValueError, KeyError, urllib.error.URLError):
                token = ''
            time.sleep(3)


if __name__ == '__main__':
    run()
