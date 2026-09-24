export const API_URL = "https://bug-free-umbrella-w9rq5gxw7qqc5p5g-8000.app.github.dev";

export async function getSignals() {
  const response = await fetch(`${API_URL}/signals`);
  if (!response.ok) throw new Error("Failed to load signals");
  const data = await response.json(); return (data.signals || []).map((x:any)=>({symbol:x.ticker,name:x.ticker,price:x.price,changePct:x.momentum_pct,relativeVolume:x.relative_volume,trend:x.trend,score:Math.min(100,Math.round(x.relative_volume*20+x.momentum_pct*10)),reason:`Momentum ${x.momentum_pct}% • RVOL ${x.relative_volume}x • ${x.trend}`,observedAt:"Live scan",invalidation:`₹${x.invalidation}`}));
}
