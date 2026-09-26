import yfinance as yf
import pandas as pd
import time

_CACHE = {"at": 0.0, "data": []}
CACHE_SECONDS = 300

# Fixed scanner universe. Edit this list to make permanent additions/removals.
SYMBOLS = ['RELIANCE.NS', 'HDFCBANK.NS', 'ICICIBANK.NS', 'BHARTIARTL.NS', 'INFY.NS', 'LT.NS', 'SBIN.NS', 'AXISBANK.NS', 'ITC.NS', 'M&M.NS', 'TCS.NS', 'KOTAKBANK.NS', 'BAJFINANCE.NS', 'HINDUNILVR.NS', 'MARUTI.NS', 'SUNPHARMA.NS', 'NTPC.NS', 'ULTRACEMCO.NS', 'TITAN.NS', 'ETERNAL.NS', 'BEL.NS', 'POWERGRID.NS', 'ASIANPAINT.NS', 'BAJAJFINSV.NS', 'HCLTECH.NS', 'TRENT.NS', 'TATASTEEL.NS', 'JSWSTEEL.NS', 'ADANIPORTS.NS', 'COALINDIA.NS', 'ONGC.NS', 'NESTLEIND.NS', 'GRASIM.NS', 'TECHM.NS', 'DRREDDY.NS', 'CIPLA.NS', 'SBILIFE.NS', 'HDFCLIFE.NS', 'SHRIRAMFIN.NS', 'JIOFIN.NS', 'ADANIENT.NS', 'EICHERMOT.NS', 'APOLLOHOSP.NS', 'BAJAJ-AUTO.NS', 'HEROMOTOCO.NS', 'TATACONSUM.NS', 'HINDALCO.NS', 'WIPRO.NS', 'INDIGO.NS', 'MAXHEALTH.NS', 'BPCL.NS', 'BRITANNIA.NS', 'INDHOTEL.NS', 'CGPOWER.NS', 'HYUNDAI.NS', 'SWIGGY.NS', 'BAJAJHFL.NS', 'VEDL.NS', 'DIVISLAB.NS', 'IOC.NS', 'VBL.NS', 'DMART.NS', 'TVSMOTOR.NS', 'CHOLAFIN.NS', 'ABB.NS', 'SIEMENS.NS', 'HAVELLS.NS', 'BOSCHLTD.NS', 'DLF.NS', 'GODREJCP.NS', 'DABUR.NS', 'MARICO.NS', 'COLPAL.NS', 'UNITDSPR.NS', 'PIDILITIND.NS', 'AMBUJACEM.NS', 'ADANIPOWER.NS', 'ADANIGREEN.NS', 'ADANIENSOL.NS', 'PFC.NS', 'RECLTD.NS', 'IRFC.NS', 'IRCTC.NS', 'PNB.NS', 'BANKBARODA.NS', 'CANBK.NS', 'UNIONBANK.NS', 'MOTHERSON.NS', 'CUMMINSIND.NS', 'BHARATFORG.NS', 'ZYDUSLIFE.NS', 'LUPIN.NS', 'TORNTPHARM.NS', 'MANKIND.NS', 'ICICIGI.NS', 'ICICIPRULI.NS', 'NAUKRI.NS', 'POLICYBZR.NS', 'LODHA.NS', 'GAIL.NS', 'AUBANK.NS', 'AUROPHARMA.NS', 'BSE.NS', 'BANDHANBNK.NS', 'BIOCON.NS', 'COFORGE.NS', 'CONCOR.NS', 'COROMANDEL.NS', 'DIXON.NS', 'FEDERALBNK.NS', 'FORTIS.NS', 'NYKAA.NS', 'GMRAIRPORT.NS', 'GODREJPROP.NS', 'HDFCAMC.NS', 'INDIANB.NS', 'INDUSTOWER.NS', 'KPITTECH.NS', 'LTF.NS', 'MFSL.NS', 'MPHASIS.NS', 'MRF.NS', 'OBEROIRLTY.NS', 'PAYTM.NS', 'OFSS.NS', 'PAGEIND.NS', 'PATANJALI.NS', 'PERSISTENT.NS', 'PHOENIXLTD.NS', 'POLYCAB.NS', 'PRESTIGE.NS', 'SONACOMS.NS', 'SRF.NS', 'SAIL.NS', 'SUZLON.NS', 'TATACOMM.NS', 'TATAELXSI.NS', 'TATATECH.NS', 'TIINDIA.NS', 'UPL.NS', 'VOLTAS.NS', 'YESBANK.NS', 'ZEEL.NS', 'KALYANKJIL.NS', 'OIL.NS', 'PETRONET.NS', 'RVNL.NS', 'IDFCFIRSTB.NS', 'MCX.NS', 'LAURUSLABS.NS', 'KARURVYSYA.NS', 'NAVINFLUOR.NS', 'DELHIVERY.NS', 'PIRAMALFIN.NS', 'CDSL.NS', 'ANGELONE.NS', 'RBLBANK.NS', 'PNBHOUSING.NS', 'CAMS.NS', 'AARTIIND.NS', 'AFFLE.NS', 'ARE&M.NS', 'BLUESTARCO.NS', 'BRIGADE.NS', 'CESC.NS', 'CERA.NS', 'CHAMBLFERT.NS', 'CUB.NS', 'CYIENT.NS', 'DEEPAKNTR.NS', 'FSL.NS', 'GLENMARK.NS', 'GUJENERGY.NS', 'HFCL.NS', 'IEX.NS', 'INDIAMART.NS', 'JUBLFOOD.NS', 'JYOTHYLAB.NS', 'KAYNES.NS', 'KEI.NS', 'KFINTECH.NS', 'MANAPPURAM.NS', 'NATIONALUM.NS', 'NCC.NS', 'NAM-INDIA.NS', 'NLCINDIA.NS', 'RADICO.NS', 'REDINGTON.NS', 'RITES.NS', 'SONATSOFTW.NS', 'SWSOLAR.NS', 'TANLA.NS', 'TATACHEM.NS', 'TEJASNET.NS', 'TRIDENT.NS', 'UCOBANK.NS', 'WELSPUNLIV.NS', 'ZENSARTECH.NS', 'ZYDUSWELL.NS', 'CUPID.NS']


def _series(data, field, ticker):
    """Return one ticker's field from a multi-ticker yfinance download."""
    try:
        s = data[field][ticker]
        return s.dropna()
    except Exception:
        return pd.Series(dtype="float64")


def signals():
    # Avoid launching a new 200-stock scan on every page refresh.
    now = time.time()
    if _CACHE["data"] and now - _CACHE["at"] < CACHE_SECONDS:
        return _CACHE["data"]
    """Scan the fixed universe and return the strongest observed momentum."""
    try:
        data = yf.download(
            SYMBOLS,
            period="1mo",
            interval="1d",
            group_by="column",
            auto_adjust=True,
            progress=False,
            threads=True,
        )
        if data.empty:
            return []

        results = []

        for ticker in SYMBOLS:
            try:
                close = _series(data, "Close", ticker)
                high = _series(data, "High", ticker)
                low = _series(data, "Low", ticker)
                volume = _series(data, "Volume", ticker)

                if min(len(close), len(high), len(low), len(volume)) < 21:
                    continue

                price = float(close.iloc[-1])
                prev = float(close.iloc[-2])
                ret_1d = ((price / prev) - 1) * 100 if prev else 0.0
                ret_5d = ((price / float(close.iloc[-6])) - 1) * 100
                ret_20d = ((price / float(close.iloc[-21])) - 1) * 100

                ema9 = close.ewm(span=9, adjust=False).mean()
                ema20 = close.ewm(span=20, adjust=False).mean()
                trend_ok = price > float(ema9.iloc[-1]) > float(ema20.iloc[-1])

                avg_vol = float(volume.iloc[-21:-1].mean())
                rvol = float(volume.iloc[-1]) / avg_vol if avg_vol > 0 else 0.0

                prior_20_high = float(high.iloc[-21:-1].max())
                breakout_pct = ((price / prior_20_high) - 1) * 100 if prior_20_high else 0.0

                tr = pd.concat([
                    high - low,
                    (high - close.shift(1)).abs(),
                    (low - close.shift(1)).abs(),
                ], axis=1).max(axis=1)
                atr14 = float(tr.tail(14).mean())
                atr_pct = (atr14 / price) * 100 if price else 0.0

                # Transparent 0-100 momentum score.
                price_score = max(0, min(25, ret_1d * 5 + ret_5d * 1.5 + ret_20d * 0.35))
                volume_score = max(0, min(20, (rvol - 0.7) * 20))
                trend_score = 20 if trend_ok else (10 if price > float(ema20.iloc[-1]) else 0)
                breakout_score = max(0, min(15, 7.5 + breakout_pct * 7.5))
                consistency_score = 10 if (ret_5d > 0 and ret_20d > 0) else (5 if ret_20d > 0 else 0)
                risk_score = max(0, min(10, 10 - max(0, atr_pct - 2) * 1.5))

                score = round(
                    price_score + volume_score + trend_score +
                    breakout_score + consistency_score + risk_score
                )

                # Keep the API focused on meaningful observed momentum.
                if score < 60 or ret_1d <= 0 or not trend_ok:
                    continue

                recent_low = float(low.tail(10).min())

                results.append({
                    "ticker": ticker,
                    "price": round(price, 2),
                    "momentum_pct": round(ret_1d, 2),
                    "return_5d_pct": round(ret_5d, 2),
                    "return_20d_pct": round(ret_20d, 2),
                    "relative_volume": round(rvol, 2),
                    "breakout_pct": round(breakout_pct, 2),
                    "atr_pct": round(atr_pct, 2),
                    "trend": "Bullish",
                    "score": int(min(100, max(0, score))),
                    "reason": (
                        f"1D {ret_1d:.2f}% • 5D {ret_5d:.2f}% • "
                        f"20D {ret_20d:.2f}% • RVOL {rvol:.2f}x • "
                        f"price above EMA9/EMA20"
                    ),
                    "invalidation": round(recent_low, 2),
                })
            except Exception:
                continue

        results.sort(key=lambda item: item["score"], reverse=True)
        _CACHE["data"] = results
        _CACHE["at"] = time.time()
        return results

    except Exception as exc:
        print("Scanner error:", exc)
        return []
