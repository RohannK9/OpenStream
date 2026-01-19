#!/bin/sh
set -eu

# Write runtime config consumed by index.html -> /config.js
API_BASE_URL="${OPENSTREAM_API_BASE_URL:-http://localhost:8000}"
GRAFANA_URL="${OPENSTREAM_GRAFANA_URL:-http://localhost:3001}"
PROM_URL="${OPENSTREAM_PROMETHEUS_URL:-http://localhost:9090}"

cat > /usr/share/nginx/html/config.js <<EOF
window.__OPENSTREAM_CONFIG__ = {
  apiBaseUrl: "${API_BASE_URL}",
  grafanaUrl: "${GRAFANA_URL}",
  prometheusUrl: "${PROM_URL}"
};
EOF

