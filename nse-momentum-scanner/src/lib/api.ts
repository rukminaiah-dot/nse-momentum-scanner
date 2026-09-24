export const API_URL = "https://bug-free-umbrella-w9rq5gxw7qqc5p5g-8000.app.github.dev";

export async function getSignals() {
  const response = await fetch(`${API_URL}/signals`);
  if (!response.ok) throw new Error("Failed to load signals");
  return response.json();
}
