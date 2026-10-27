import json
from pathlib import Path
import subprocess


def test_live_quote_columns_and_sell_completion_are_separate_from_signal_price():
    html=Path('v2/frontend/index.html').read_text()
    render='function renderPaperStockScreen(){'+html.split('function renderPaperStockScreen(){',1)[1].split('function refreshPaperStockScreen(){',1)[0]
    script='''
const elements={},$=id=>elements[id]??(elements[id]={textContent:'',innerHTML:''});
const document={createElement:()=>({})};
const esc=x=>String(x??'—'),num=(x,n=2)=>Number(x).toFixed(n);
const table=(headers,body)=>headers.join('|')+body,tr=values=>values.join('|'),renderFavourite15m=()=>{};
const state={board:[{symbol:'TEST',quote_price:123.45,daily_change_pct:2.5,change_status:'CURRENT',quote_time_ist:'2026-10-27T10:01:00+05:30'}],
paperStockScreen:{session_date:'2026-10-27',status:'READY',completed:[{symbol:'DONE',sell_price:111,sell_time:'10:00',completion_basis:'SELL_WITHOUT_PRIOR_BUY'}]},
paperQualifiedStocks:[{symbol:'TEST',relative_volume:.8,signal:'PAPER_BUY',signal_fresh:true,lifecycle:'BUY_ACTIVE',candle:{close:100},details:{stoch_k:18,stoch_d:17}}]};
''' + render + '''
renderPaperStockScreen();console.log(JSON.stringify({table:elements['paper-stock-screen'].innerHTML,completed:elements['paper-shortlist-completed'].innerHTML}));
'''
    result=subprocess.run(['node','-e',script],capture_output=True,text=True,check=True)
    data=json.loads(result.stdout)
    assert '123.45' in data['table'] and '2.50%' in data['table'] and '0.800×' in data['table']
    assert 'Live quote' in data['table'] and 'BUY_ACTIVE' in data['table']
    assert '18.00 / 17.00' in data['table']
    assert 'DONE' in data['completed'] and 'No prior BUY recorded' in data['completed']
    assert 'Not applicable' in data['completed']
