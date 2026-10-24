#!/usr/bin/env python3
"""Start the complete local Pages emulator and restart-safe collector supervisor."""
import json
import os
from pathlib import Path
import secrets
import signal
import socket
import subprocess
import sys
import time
from urllib.request import urlopen

ROOT=Path(__file__).resolve().parents[1]
os.chdir(ROOT)
variables=ROOT/'.dev.vars'
if not variables.exists():
    persistent=ROOT/'.wrangler/local-secrets.env'
    persistent.parent.mkdir(parents=True,exist_ok=True)
    if not persistent.exists():
        fd=os.open(persistent,os.O_WRONLY|os.O_CREAT|os.O_EXCL,0o600)
        with os.fdopen(fd,'w') as f:
            f.write('INGEST_TOKEN='+secrets.token_urlsafe(32)+'\nREFRESH_TOKEN='+secrets.token_urlsafe(32)+'\n')
    fd=os.open(variables,os.O_WRONLY|os.O_CREAT|os.O_EXCL,0o600)
    with os.fdopen(fd,'w') as f:
        f.write(persistent.read_text())
values=dict(line.split('=',1) for line in variables.read_text().splitlines() if '=' in line)
with socket.socket() as probe:
    probe.bind(('127.0.0.1',8788))
subprocess.run(['npm','run','build'],check=True)
subprocess.run(['npx','wrangler','d1','migrations','apply','film-tonight','--local'],check=True)
api=subprocess.Popen(['npx','wrangler','pages','dev','dist','--ip','127.0.0.1','--port','8788','--persist-to','.wrangler/state'],start_new_session=True)
collector=None
def stop(*_):
    for child in (collector,api):
        if child and child.poll() is None:os.killpg(child.pid,signal.SIGTERM)
    for child in (collector,api):
        if child:
            try:child.wait(timeout=10)
            except subprocess.TimeoutExpired:os.killpg(child.pid,signal.SIGKILL)
signal.signal(signal.SIGTERM,lambda *_:sys.exit(0))
try:
    for _ in range(60):
        if api.poll() is not None:raise RuntimeError('API startup failed')
        try:
            with urlopen('http://127.0.0.1:8788/api/v1/ready',timeout=1) as r:
                if r.status==200:break
        except Exception:time.sleep(1)
    else:raise RuntimeError('API readiness timeout')
    env={**os.environ,'FILM_API_URL':'http://127.0.0.1:8788','FILM_INGEST_TOKEN':values['INGEST_TOKEN']}
    collector=subprocess.Popen([sys.executable,'collector_job.py','--watch',os.environ.get('REFRESH_INTERVAL','600')],env=env,start_new_session=True)
    while api.poll() is None and collector.poll() is None:time.sleep(1)
    raise RuntimeError('Local service process stopped; restart supervisor')
finally:stop()
