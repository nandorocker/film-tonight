import importlib.util
import json
from pathlib import Path
import sys
import unittest
from unittest.mock import patch

ROOT=Path(__file__).resolve().parents[1]
sys.path.insert(0,str(ROOT/'agent'))
import client
import mcp_stdio

class AgentTests(unittest.TestCase):
    def test_private_profile_origin_stays_out_of_search_and_coverage_output(self):
        origin=[14.456789123,50.123456789]
        cfg={'origin':origin,'api_url':'https://public.example'}
        data={'venues':[],'snapshots':[],'attempts':[]}
        with patch.object(client,'config',return_value=cfg),patch.object(client,'request',return_value=data) as request:
            for fn in (client.search_screenings,client.get_coverage):
                result=fn({'date':'2026-10-24'})
                encoded=json.dumps(result)
                self.assertNotIn(str(origin[0]),encoded);self.assertNotIn(str(origin[1]),encoded)
                self.assertTrue(result['filters']['origin_supplied'])
            self.assertEqual(request.call_args.args[0],'snapshot?date=2026-10-24')

    def test_mcp_tool_contract(self):
        self.assertEqual(len(mcp_stdio.dispatch({'method':'tools/list'})['tools']),3)
        with patch.object(mcp_stdio,'search_screenings',return_value={'total':0,'screenings':[]}):
            r=mcp_stdio.dispatch({'method':'tools/call','params':{'name':'search_screenings','arguments':{}}})
            self.assertEqual(json.loads(r['content'][0]['text'])['total'],0)
        with self.assertRaises(ValueError):mcp_stdio.dispatch({'method':'tools/call','params':{'name':'refresh_screenings','arguments':{'url':'https://arbitrary.example'}}})

if __name__=='__main__':unittest.main()
