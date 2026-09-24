import yfinance as yf
SYMBOLS=["RELIANCE.NS","TCS.NS","HDFCBANK.NS","ICICIBANK.NS","INFY.NS"]
def scan():
    data = yf.download(SYMBOLS, period="5d", interval="15m", progress=False)
    print("SCANNER DATA OK:", len(data), "candles")

if __name__ == "__main__":
    scan()

def momentum():
    d=yf.download(SYMBOLS,period="5d",interval="15m",progress=False)
    c=d["Close"].ffill()
    return ((c.iloc[-1]/c.iloc[-2]-1)*100).round(2).sort_values(ascending=False)

def volume_strength():
    d=yf.download(SYMBOLS,period="5d",interval="15m",progress=False)
    v=d["Volume"].fillna(0)
    return (v.iloc[-1]/v.tail(20).mean()).round(2).sort_values(ascending=False)

def candidates():
    m=momentum()
    v=volume_strength()
    return [{"ticker":x,"momentum_pct":float(m[x]),"relative_volume":float(v[x])} for x in m.index if m[x]>0 and v[x]>=1.0]

def candidates():
    m=momentum()
    v=volume_strength()
    return [{"ticker":x,"momentum_pct":float(m[x]),"relative_volume":float(v[x])} for x in m.index if m[x]>0 and v[x]>=1.0]

def prices():
    d=yf.download(SYMBOLS,period="5d",interval="15m",progress=False)
    return d["Close"].ffill().iloc[-1].round(2)



def signals():
    p=prices()
    return [{**x,"price":float(p[x["ticker"]])} for x in candidates()]
