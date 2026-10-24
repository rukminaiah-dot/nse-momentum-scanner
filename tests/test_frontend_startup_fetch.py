"""Execute the browser's real JSON fetch helper with deterministic transport failures."""
import json
import pathlib
import re
import subprocess
import unittest

ROOT = pathlib.Path(__file__).resolve().parents[1]


class FrontendStartupFetchTests(unittest.TestCase):
    def run_case(self, scenario):
        html = (ROOT / 'v2/frontend/index.html').read_text()
        helper = html.split('async function get(path){', 1)[1].split('\nfunction table(', 1)[0]
        helper = 'async function get(path){' + helper
        program = '''
const scenario=JSON.parse(process.argv[1]);let calls=0,waits=[],options=[];const elements={};
const state={apiReady:false};const $=id=>elements[id]??(elements[id]={textContent:''});
const setTimeout=(fn,ms)=>{if(ms!==12000){waits.push(ms);fn()}return 1};const clearTimeout=()=>{};
const fetch=async(path,opts)=>{options.push({path,accept:opts.headers.Accept,cache:opts.cache});
const item=scenario[Math.min(calls++,scenario.length-1)];
if(item.error){const e=new Error(item.error);e.name=item.name||'Error';throw e}
return {ok:item.status>=200&&item.status<300,status:item.status,headers:{get:()=>item.type},json:async()=>item.body};};
''' + helper + '''
get('/api/v2/scanner').then(value=>console.log(JSON.stringify({value,calls,waits,options,elements})))
.catch(error=>console.log(JSON.stringify({error:error.message,calls,waits,options,elements})));
'''
        result = subprocess.run(['node', '-e', program, json.dumps(scenario)], capture_output=True, text=True, check=True, timeout=10)
        return json.loads(result.stdout)

    def test_render_html_loading_page_is_retried_until_json_arrives(self):
        result = self.run_case([{'status': 200, 'type': 'text/html'}, {'status': 503, 'type': 'text/html'},
                                {'status': 200, 'type': 'application/json', 'body': [{'symbol': 'NIFTY 50', 'price': 22600}]}])
        self.assertEqual(result['calls'], 3)
        self.assertEqual(result['value'][0]['price'], 22600)
        self.assertTrue(all(x['accept'] == 'application/json' and x['cache'] == 'no-store' for x in result['options']))
        self.assertIn('retrying automatically', result['elements']['session']['textContent'])

    def test_timeouts_retry_but_permanent_authentication_errors_do_not(self):
        result = self.run_case([{'error': 'aborted', 'name': 'AbortError'}, {'status': 200, 'type': 'application/json', 'body': []}])
        self.assertEqual(result['calls'], 2)
        denied = self.run_case([{'status': 401, 'type': 'application/json'}])
        self.assertEqual(denied['calls'], 1)
        self.assertEqual(denied['error'], 'HTTP 401')

    def test_unavailable_service_stops_after_bounded_attempts_without_inventing_data(self):
        result = self.run_case([{'status': 503, 'type': 'text/html'}])
        self.assertEqual(result['calls'], 6)
        self.assertEqual(result['error'], 'API_STARTUP_TIMEOUT')
        self.assertNotIn('value', result)
        self.assertLessEqual(sum(result['waits']), 40000)
