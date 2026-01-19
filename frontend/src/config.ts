export type RuntimeConfig = {
  apiBaseUrl: string;
  grafanaUrl: string;
  prometheusUrl: string;
};

function normalizeBaseUrl(u: string): string {
  return u.replace(/\/+$/, "");
}

export function getConfig(): RuntimeConfig {
  const w = window.__OPENSTREAM_CONFIG__ || {};

  const apiBaseUrl =
    w.apiBaseUrl || (import.meta as any).env?.VITE_API_BASE_URL || "http://localhost:8000";
  const grafanaUrl =
    w.grafanaUrl || (import.meta as any).env?.VITE_GRAFANA_URL || "http://localhost:3001";
  const prometheusUrl =
    w.prometheusUrl || (import.meta as any).env?.VITE_PROMETHEUS_URL || "http://localhost:9090";

  return {
    apiBaseUrl: normalizeBaseUrl(apiBaseUrl),
    grafanaUrl: normalizeBaseUrl(grafanaUrl),
    prometheusUrl: normalizeBaseUrl(prometheusUrl)
  };
}

