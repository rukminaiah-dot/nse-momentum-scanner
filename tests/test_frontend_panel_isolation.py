"""Exercise actual mobile stock and market-factor renderers without a live account."""
import json
import pathlib
import subprocess
import unittest

ROOT = pathlib.Path(__file__).resolve().parents[1]


class FrontendPanelIsolationTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.html = (ROOT / 'v2/frontend/index.html').read_text()

    def js(self, script):
        result = subprocess.run(['node', '-e', script], text=True, capture_output=True, timeout=10)
        self.assertEqual(result.returncode, 0, result.stderr)
        return json.loads(result.stdout)

    def test_optional_panel_failure_cannot_prevent_two_hundred_stock_tiles(self):
        board = 'function renderBoard(){' + self.html.split('function renderBoard(){', 1)[1].split('\nasync function renderPnlChart', 1)[0]
        safe = 'function renderSafely(' + self.html.split('function renderSafely(', 1)[1].split('\nlet reversalRequest', 1)[0]
        program = '''
const elements={},$=id=>elements[id]??(elements[id]={value:'',textContent:'',innerHTML:''});
const document={querySelectorAll:()=>[]};const renderFailures=new Set();
const esc=v=>String(v??'—'),num=(v)=>v==null?'—':Number(v).toFixed(2);
const normalizeBoardSearch=v=>String(v||'').toUpperCase(),getFavourites=()=>[];
const fresh=()=>false,verifiedCandleScore=()=>false,dailyChangeSort=(a,b)=>a.symbol.localeCompare(b.symbol);
const hasVerifiedDailyChange=x=>Number.isFinite(x.daily_change_pct),renderFavourite15m=()=>{};
const buttonSymbol=s=>'<button>'+s+'</button>';
const table=(headers,rows)=>rows.join(''),tr=cells=>cells.join('|');
const state={rows:[],ratings:[],lastRatings:{},historicalRatings:[],board:Array.from({length:200},(_,i)=>({symbol:'TEST'+i,last_price:100,quote_price:101,daily_change_pct:1,change_status:'LAST_SESSION'}))};
let boardFilter='ALL';
''' + safe + board + '''
renderSafely('Optional pre-market panel',()=>{throw Error('malformed optional data')});
renderSafely('Stock list',renderBoard);
console.log(JSON.stringify({tiles:(elements['board-mobile'].innerHTML.match(/<article /g)||[]).length,
status:elements['board-change-status'].textContent,failures:[...renderFailures],hasLast:elements['board-mobile'].innerHTML.includes('TEST199')}));
'''
        result = self.js(program)
        self.assertEqual(result['tiles'], 200)
        self.assertTrue(result['hasLast'])
        self.assertIn('200 of 200', result['status'])
        self.assertEqual(result['failures'], ['Optional pre-market panel'])
        self.assertIn('.mobile-stock-list{display:block!important}', self.html)

    def test_factor_panel_distinguishes_loading_from_real_historical_values(self):
        band = 'function factorBand(' + self.html.split('function factorBand(', 1)[1].split('\nfunction renderMarketFactorBands', 1)[0]
        render = 'function renderMarketFactorBands(){' + self.html.split('function renderMarketFactorBands(){', 1)[1].split('\nfunction reversalEvidenceAssessment', 1)[0]
        news = (ROOT / 'v2/frontend/news_trend_relation.js').read_text()
        result = self.js('''
const elements={},$=id=>elements[id]??(elements[id]={innerHTML:''});
const esc=v=>String(v??'—'),num=v=>v==null?'—':Number(v).toFixed(2);
const window={classifyNewsTrendRelation:require('./v2/frontend/news_trend_relation.js')};
const state={reversalContext:null,premarket:{news:[]}};
''' + band + render + '''
renderMarketFactorBands();const loading=elements['pm-factor-bands'].innerHTML;
state.reversalContext={market_session:'CLOSED',nifty_pe:{status:'HISTORICAL',value:19.26,session_date:'2026-10-22',history:[]},india_vix:{status:'HISTORICAL',value:16.86,change_pct:6.98,as_of:'2026-10-23T10:30:00Z'},institutional_flows:{status:'AVAILABLE',as_of_date:'2026-10-23',freshness:'CURRENT',fii:{latest:{date:'2026-10-23',net_cr:887.65}},dii:{latest:{date:'2026-10-23',net_cr:3235.36}}}};
renderMarketFactorBands();console.log(JSON.stringify({loading,loaded:elements['pm-factor-bands'].innerHTML}));
''')
        self.assertIn('Loading timestamped', result['loading'])
        self.assertNotIn('No verified daily', result['loading'])
        self.assertIn('P/E 19.26', result['loaded'])
        self.assertIn('India VIX 16.86', result['loaded'])
        self.assertIn('historical / last quote', result['loaded'])
        self.assertIn('Both net buying', result['loaded'])
        self.assertIn('887.65', result['loaded'])
        self.assertIn('3235.36', result['loaded'])
