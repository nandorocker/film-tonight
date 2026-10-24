#!/usr/bin/env python3
"""Thin MCP JSON-RPC stdio wrapper; no separate cache, scraper, or model."""
import json
import sys
from client import search_screenings,get_coverage,refresh_screenings

SEARCH_SCHEMA={'type':'object','properties':{
    'date':{'type':'string','description':'YYYY-MM-DD, Europe/Prague'},'after':{'type':'string','default':'18:00'},
    'remaining':{'type':'boolean','default':True},'buffer_minutes':{'type':'number','minimum':0,'maximum':240},
    'q':{'type':'string'},'venue':{'type':'string'},'format':{'type':'string'},
    'access':{'enum':['confirmed','all','english_audio','english_subtitles','english_friendly','unknown','conflict','not_english']},
    'origin':{'type':['array','null'],'items':{'type':'number'},'minItems':2,'maxItems':2,'description':'[longitude,latitude], only used locally'},
    'radius_km':{'type':['number','null'],'exclusiveMinimum':0}},'additionalProperties':False}
TOOLS=[{'name':name,'description':description,'inputSchema':schema} for name,description,schema in [
    ('search_screenings','Search cached Prague screenings; no provider crawling. Private origin stays local.',SEARCH_SCHEMA),
    ('get_coverage','Read freshness and venue/date gaps.',SEARCH_SCHEMA),
    ('refresh_screenings','Queue an authenticated refresh for the next collection run, not immediate crawling.',{'type':'object','properties':{},'additionalProperties':False})]]

def dispatch(message):
    method=message.get('method');params=message.get('params') or {}
    if method=='initialize':return {'protocolVersion':'2024-11-05','capabilities':{'tools':{}},'serverInfo':{'name':'film-tonight','version':'1.0.0'}}
    if method=='ping':return {}
    if method=='tools/list':return {'tools':TOOLS}
    if method=='tools/call':
        name=params.get('name');args=params.get('arguments') or {}
        if name not in {'search_screenings','get_coverage','refresh_screenings'}:raise ValueError('Unknown tool')
        if not isinstance(args,dict) or any(k not in SEARCH_SCHEMA['properties'] for k in args):raise ValueError('Unknown arguments')
        if name=='refresh_screenings' and args:raise ValueError('Refresh accepts no arguments')
        try:
            value=refresh_screenings() if name=='refresh_screenings' else {'search_screenings':search_screenings,'get_coverage':get_coverage}[name](args)
            return {'content':[{'type':'text','text':json.dumps(value,ensure_ascii=False)}]}
        except Exception:
            return {'isError':True,'content':[{'type':'text','text':'Movie service unavailable; check configuration and cached coverage. No showtimes can be confirmed.'}]}
    raise ValueError('Method not found')

def main():
    while True:
        line=sys.stdin.readline(65537)
        if not line:break
        message=None
        try:
            if len(line)>65536:raise ValueError('Message too large')
            message=json.loads(line)
            if 'id' not in message:continue
            result=dispatch(message);response={'jsonrpc':'2.0','id':message['id'],'result':result}
        except Exception:
            response={'jsonrpc':'2.0','id':message.get('id') if isinstance(locals().get('message'),dict) else None,'error':{'code':-32602,'message':'Invalid MCP request'}}
        print(json.dumps(response,ensure_ascii=False),flush=True)

if __name__=='__main__':main()
