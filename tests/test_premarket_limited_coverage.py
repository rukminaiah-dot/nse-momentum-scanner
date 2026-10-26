"""Run the actual pre-market decision code against Monday quote coverage."""
import json
from pathlib import Path
import subprocess
import unittest


class PremarketCoverageTests(unittest.TestCase):
    def test_current_asian_quotes_are_usable_without_relabeling_friday_closes(self):
        html = (Path(__file__).resolve().parents[1] / 'v2/frontend/index.html').read_text()
        decision = html.split('function renderPre(){', 1)[1].split("$('pm-nifty')", 1)[0]
        program = """
const now=Date.parse('2026-10-26T01:43:34Z'); Date.now=()=>now;
const indexRow=()=>undefined, num=(x)=>Number(x).toFixed(2);
function quote(name, change, age=20){return {name,status:'QUOTED',price:100,
previous_close:99,change_pct:change,last_trade_at:new Date(now-age*1000).toISOString(),latency:'120 Seconds'}};
function decide(instruments){const state={sessionOpen:false,premarket:{instruments}};
""" + decision + """return {bias,reason};}
const friday=quote('DOW JONES',-1,200000);
const cases=[
 [quote('GIFT NIFTY',.05),quote('HANG SENG',-.2),quote('NIKKEI 225',-.1),friday],
 [quote('GIFT NIFTY',.5),quote('HANG SENG',.2),quote('NIKKEI 225',.1)],
 [quote('GIFT NIFTY',-.5),quote('HANG SENG',-.2),quote('NIKKEI 225',-.1)],
 [quote('GIFT NIFTY',.5,2000),quote('HANG SENG',.2),quote('NIKKEI 225',.1)],
 [quote('GIFT NIFTY',.5),quote('HANG SENG',.2),friday],
 [quote('GIFT NIFTY',.5),quote('HANG SENG',.2),quote('NIKKEI 225',.1),quote('FTSE 100',.1)],
]; console.log(JSON.stringify(cases.map(decide)));
"""
        result = subprocess.run(['node', '-e', program], capture_output=True, text=True, timeout=10)
        self.assertEqual(result.returncode, 0, result.stderr)
        rows = json.loads(result.stdout)
        self.assertEqual(rows[0]['bias'], 'LIMITED PRE-MARKET CUES · MIXED')
        self.assertNotIn('DOW JONES', rows[0]['reason'])
        self.assertIn('historical', rows[0]['reason'])
        self.assertEqual(rows[1]['bias'], 'LIMITED PRE-MARKET CUES · BULLISH')
        self.assertEqual(rows[2]['bias'], 'LIMITED PRE-MARKET CUES · BEARISH')
        for row in rows[3:5]:
            self.assertEqual(row['bias'], 'PRE-MARKET CUES UNAVAILABLE')
        self.assertEqual(rows[5]['bias'], 'INDICATIVE PRE-MARKET · BULLISH')
