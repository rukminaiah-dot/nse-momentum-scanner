"""Daily lifecycle invariants: retention, idempotency, persistence and quote rendering."""
import copy
from datetime import datetime, timedelta
from pathlib import Path
from tempfile import TemporaryDirectory
from unittest.mock import patch
from v2.backend.daily_shortlist import ShortlistStore, advance_day, empty_day, IST, DailyShortlist
from v2.backend.experimental_15m_volume import verified_15m_same_slot_average


def fixture():
    day = datetime(2026, 10, 27, 9, 15)
    dates=[]
    prior=day-timedelta(days=1)
    while len(dates)<20:
        if prior.weekday()<5:
            dates.append(prior)
        prior-=timedelta(days=1)
    history=[dict(timestamp=d+timedelta(minutes=15*i),open=100,high=102,low=99,close=101,volume=100)
             for d in sorted(dates) for i in range(25)]
    today=[dict(timestamp=day+timedelta(minutes=15*i),open=100,high=102,low=99,close=101,volume=150) for i in range(4)]
    return history, today


def test_qualifies_at_boundary_then_analyzes_below_threshold_and_completes_once():
    history,today=fixture();state=empty_day(today[0]['timestamp'].date())
    def step(index, signal):
        bars=history+today[:index+1]
        with patch('v2.backend.daily_shortlist.evaluate',return_value={'signal':signal,'reason':'TEST'}) as evaluate:
            advance_day(state,'TEST',bars,history,today[index]['timestamp']+timedelta(minutes=15))
        return evaluate
    step(0,'WAIT')
    assert state['selected'][0]['qualification_rvol']==1.5
    today[1]['volume']=50
    evaluated=step(1,'PAPER_BUY')
    assert evaluated.call_args.kwargs['settings'].min_rvol==0
    assert state['selected'][0]['relative_volume']==.5
    assert state['selected'][0]['lifecycle']=='BUY_ACTIVE'
    step(2,'WAIT')
    step(3,'PAPER_SELL')
    assert state['selected']==[]
    assert len(state['completed'])==1
    assert state['completed'][0]['buy_price']==101
    assert state['completed'][0]['sell_price']==101
    assert state['completed'][0]['gross_pnl_per_share']==0
    step(3,'PAPER_SELL')
    assert len(state['completed'])==1


def test_low_volume_new_stock_is_not_shortlisted():
    history,today=fixture();today[-1]['volume']=149
    state=empty_day(today[0]['timestamp'].date())
    with patch('v2.backend.daily_shortlist.evaluate') as evaluate:
        advance_day(state,'LOW',history+today,history,today[-1]['timestamp']+timedelta(minutes=15))
    assert state['selected']==[]
    evaluate.assert_not_called()


def test_sell_without_buy_has_no_invented_profit():
    history,today=fixture();state=empty_day(today[0]['timestamp'].date())
    with patch('v2.backend.daily_shortlist.evaluate',return_value={'signal':'PAPER_SELL','reason':'TEST'}):
        advance_day(state,'TEST',history+today,history,today[-1]['timestamp']+timedelta(minutes=15))
    assert state['completed'][0]['gross_pnl_per_share'] is None
    assert state['completed'][0]['completion_basis']=='SELL_WITHOUT_PRIOR_BUY'


def test_strict_volume_requires_all_25_slots_of_last_20_sessions():
    history,today=fixture()
    assert verified_15m_same_slot_average(today[-1],history,require_full_sessions=True)==100
    assert verified_15m_same_slot_average(today[-1],history[1:],require_full_sessions=True) is None


def test_restart_preserves_rows_and_next_day_does_not_reuse_old_qualifications():
    history,today=fixture();state=empty_day(today[0]['timestamp'].date())
    with patch('v2.backend.daily_shortlist.evaluate',return_value={'signal':'WAIT','reason':'TEST'}):
        advance_day(state,'TEST',history+today,history,today[-1]['timestamp']+timedelta(minutes=15))
    with TemporaryDirectory() as path:
        file=Path(path)/'state.db'
        ShortlistStore(file,pg_url='').write(state)
        store=ShortlistStore(file,pg_url='')
        assert store.read(state['session_date'])==state
        assert store.read('2026-10-28')['selected']==[]
        service=DailyShortlist(store)
        now=(today[-1]['timestamp']+timedelta(hours=1)).replace(tzinfo=IST)
        assert service.snapshot(now)['selected'][0]['signal_fresh'] is False


def test_older_replayed_candle_cannot_rewind_live_lifecycle():
    history,today=fixture();state=empty_day(today[0]['timestamp'].date())
    with patch('v2.backend.daily_shortlist.evaluate',return_value={'signal':'PAPER_BUY','reason':'TEST'}):
        advance_day(state,'TEST',history+today,history,today[-1]['timestamp']+timedelta(minutes=15))
    before=copy.deepcopy(state)
    with patch('v2.backend.daily_shortlist.evaluate') as evaluate:
        advance_day(state,'TEST',history+today[:1],history,today[0]['timestamp']+timedelta(minutes=15))
    assert state==before
    evaluate.assert_not_called()


def test_day_rollover_carries_active_buy_but_not_unbought_watch_rows():
    with TemporaryDirectory() as path:
        store=ShortlistStore(Path(path)/'state.db',pg_url='')
        previous=empty_day('2026-10-27')
        previous['selected']=[{'symbol':'BOUGHT','buy_time':'2026-10-27T10:00:00+05:30'}, {'symbol':'WATCH'}]
        store.write(previous)
        current=empty_day('2026-10-28')
        store.carry_active(current)
        assert [x['symbol'] for x in current['selected']]==['BOUGHT']
        assert store.read('2026-10-27')['selected']==previous['selected']


def test_worker_discovers_earlier_qualification_and_keeps_monitoring_current_lower_volume():
    history,today=fixture();today[-1]['volume']=50
    with TemporaryDirectory() as path:
        service=DailyShortlist(ShortlistStore(Path(path)/'state.db',pg_url=''))
        now=(today[-1]['timestamp']+timedelta(minutes=15)).replace(tzinfo=IST)
        with patch('v2.backend.daily_shortlist.NIFTY_200',{'TEST':'KEY'}), patch('v2.backend.daily_shortlist.fetch_symbol',return_value=(history+today,history)):
            service.scan(now,object())
        result=service.snapshot(now)
        assert result['status']=='READY'
        assert len(result['selected'])==1
        assert result['selected'][0]['first_qualified_candle']==today[0]['timestamp'].isoformat()
        assert result['selected'][0]['candle_time']==today[-1]['timestamp'].isoformat()
        assert result['selected'][0]['relative_volume']==.5
        assert result['selected'][0]['signal_fresh'] is True
        assert 'stoch_k' in result['selected'][0]['details']


def test_provider_cooldown_preserves_shortlist_and_stops_outbound_work():
    from v2.backend.history_transport import HistoryRequestError
    history,today=fixture();state=empty_day(today[0]['timestamp'].date())
    with patch('v2.backend.daily_shortlist.evaluate',return_value={'signal':'WAIT','reason':'TEST'}):
        advance_day(state,'TEST',history+today,history,today[-1]['timestamp']+timedelta(minutes=15))
    with TemporaryDirectory() as path:
        store=ShortlistStore(Path(path)/'state.db',pg_url='');store.write(state)
        service=DailyShortlist(store)
        now=(today[-1]['timestamp']+timedelta(minutes=15)).replace(tzinfo=IST)
        with patch('v2.backend.daily_shortlist.NIFTY_200',{'TEST':'KEY','OTHER':'OTHERKEY'}), patch('v2.backend.daily_shortlist.fetch_symbol',side_effect=HistoryRequestError(429,300)) as fetch:
            assert service.scan(now,object()) is False
        assert fetch.call_count==1
        result=service.snapshot(now)
        assert result['status']=='PROVIDER_COOLDOWN'
        assert len(result['selected'])==1
        assert result['retry_at_ist']
