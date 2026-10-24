"""Tail only sanitized edge outcomes/timings. Never persist request headers/bodies."""
import json
import argparse
import signal
import subprocess
import sys
from urllib.parse import urlsplit

if __name__=='__main__':
    parser=argparse.ArgumentParser();parser.add_argument('deployment',help='Deployment ID or URL returned by Pages deploy');args=parser.parse_args()
    process=subprocess.Popen(['npx','wrangler','pages','deployment','tail',args.deployment,'--project-name','film-tonight','--format','json'],stdout=subprocess.PIPE,stderr=subprocess.DEVNULL,text=True,start_new_session=True)
    def stop(*_):
        import os
        os.killpg(process.pid,signal.SIGTERM)
        raise SystemExit
    signal.signal(signal.SIGTERM,stop)
    decoder=json.JSONDecoder();buffer=''
    try:
        for line in process.stdout:
            buffer+=line
            if len(buffer)>1_000_000:buffer='';continue
            while '{' in buffer:
                buffer=buffer[buffer.index('{'):]
                try:event,end=decoder.raw_decode(buffer)
                except json.JSONDecodeError:break
                buffer=buffer[end:]
                if not isinstance(event,dict):continue
                request=(event.get('event') or {}).get('request') or {}
                print(json.dumps({'timestamp':event.get('eventTimestamp'),'outcome':event.get('outcome'),
                                  'cpu_ms':event.get('cpuTime'),'wall_ms':event.get('wallTime'),
                                  'method':request.get('method'),'path':urlsplit(request.get('url','')).path,
                                  'available_metric_keys':[k for k in event if 'time' in k.lower() or 'metric' in k.lower()]}),flush=True)
        status=process.wait()
        if status:
            print('Edge tail failed; metrics are unavailable. Check deployment access/authentication privately.',file=sys.stderr)
            raise SystemExit(1)
    finally:
        if process.poll() is None:
            import os
            os.killpg(process.pid,signal.SIGTERM)
