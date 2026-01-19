import { getConfig } from "./config";
import type { MetricsSummary } from "./types";

const TOKEN_KEY = "openstream_token";

export function getToken(): string | null {
  return localStorage.getItem(TOKEN_KEY);
}

export function setToken(token: string) {
  localStorage.setItem(TOKEN_KEY, token);
}

export function clearToken() {
  localStorage.removeItem(TOKEN_KEY);
}

function authHeaders(): Record<string, string> {
  const t = getToken();
  return t ? { Authorization: `Bearer ${t}` } : {};
}

export async function mintToken(params: {
  sub: string;
  role: "producer" | "consumer" | "admin";
  admin_secret: string;
}): Promise<string> {
  const { apiBaseUrl } = getConfig();
  const res = await fetch(`${apiBaseUrl}/v1/auth/token`, {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify(params)
  });
  if (!res.ok) {
    if (res.status === 403) {
      throw new Error(
        "Token mint failed: 403 (AUTH_ADMIN_SECRET mismatch). If you're using docker-compose defaults, the secret is 'dev-admin-secret'."
      );
    }
    throw new Error(`Token mint failed: ${res.status}`);
  }
  const data = (await res.json()) as { token: string };
  return data.token;
}

export async function fetchSummary(): Promise<MetricsSummary> {
  const { apiBaseUrl } = getConfig();
  const res = await fetch(`${apiBaseUrl}/v1/metrics/summary`, {
    headers: { ...authHeaders() }
  });
  if (res.status === 401) throw new Error("unauthorized");
  if (!res.ok) throw new Error(`summary failed: ${res.status}`);
  return (await res.json()) as MetricsSummary;
}

export async function fetchMetricsText(): Promise<string> {
  const { apiBaseUrl } = getConfig();
  // prometheus_client ASGI app redirects /metrics -> /metrics/
  const res = await fetch(`${apiBaseUrl}/metrics/`);
  if (!res.ok) throw new Error(`metrics failed: ${res.status}`);
  return await res.text();
}

export function parseCounter(metricsText: string, name: string): number {
  // Sum across all label sets:
  // openstream_ingest_events_total{topic="t",partition="0"} 123
  const re = new RegExp(`^${name}\\{[^}]*\\}\\s+([0-9.]+)\\s*$`, "gm");
  let m: RegExpExecArray | null;
  let sum = 0;
  while ((m = re.exec(metricsText)) !== null) {
    sum += Number(m[1] || 0);
  }
  return sum;
}

