export type LiveSignal = {
  ticker: string;
  price: number;
  momentum_pct: number;
  relative_volume: number;
  trend: string;
  score: number;
  reason: string;
  invalidation: number;
};

export const API_URL =
  "https://bug-free-umbrella-w9rq5gxw7qqc5p5g-8000.app.github.dev";

export async function getSignals(): Promise<LiveSignal[]> {
  const response = await fetch(`${API_URL}/signals`);

  if (!response.ok) {
    throw new Error("Failed to load signals");
  }

  const data = await response.json();
  return data.signals ?? [];
}
