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

export const API_URL = "https://nse-momentum-scanner-api.onrender.com";
  "https://nse-momentum-scanner-api.onrender.com";

const sleep = (ms: number) =>
  new Promise(resolve => setTimeout(resolve, ms));

async function apiRequest(path: string, options?: RequestInit) {
  const isRead = !options?.method || options.method === "GET";
  const attempts = isRead ? 5 : 1;
  let lastError: unknown;

  for (let attempt = 1; attempt <= attempts; attempt++) {
    try {
      const response = await fetch(`${API_URL}${path}`, options);

      if (!response.ok) {
        const message = await response.text();
        throw new Error(message || `Request failed: ${response.status}`);
      }

      return await response.json();
    } catch (error) {
      lastError = error;

      if (attempt < attempts) {
        await sleep(attempt * 3000);
      }
    }
  }

  throw lastError instanceof Error
    ? lastError
    : new Error("Unable to reach scanner API.");
}

export async function getSignals(): Promise<LiveSignal[]> {
  const data = await apiRequest("/signals");
  return data.signals ?? [];
}

export async function getUniverse(): Promise<string[]> {
  const data = await apiRequest("/universe");
  return data.symbols ?? [];
}

export async function addScrip(ticker: string) {
  return apiRequest("/universe", {
    method: "POST",
    headers: {"Content-Type": "application/json"},
    body: JSON.stringify({ticker}),
  });
}

export async function removeScrip(ticker: string) {
  const normalized = ticker.trim().toUpperCase();

  return apiRequest(
    `/universe/${encodeURIComponent(normalized)}`,
    {method: "DELETE"}
  );
}
