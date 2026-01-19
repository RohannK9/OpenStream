<script setup lang="ts">
import { computed, onMounted, onUnmounted, ref } from "vue";
import { clearToken, fetchMetricsText, fetchSummary, getToken, mintToken, parseCounter, setToken } from "./api";
import { getConfig } from "./config";
import type { MetricsSummary, TopicStat } from "./types";

const cfg = getConfig();

const token = ref<string | null>(getToken());
const sub = ref("dashboard");
const role = ref<"producer" | "consumer" | "admin">("admin");
const adminSecret = ref("dev-admin-secret");
const authError = ref<string | null>(null);

const summary = ref<MetricsSummary | null>(null);
const error = ref<string | null>(null);
const selectedTopic = ref<string>("");

const ingestRateEps = ref<number | null>(null);
let lastIngestTotal: number | null = null;
let lastIngestTs: number | null = null;

const topics = computed<TopicStat[]>(() => summary.value?.topics ?? []);
const topic = computed(() => topics.value.find((t) => t.topic === selectedTopic.value) || null);

const redisMem = computed(() => summary.value?.redis?.used_memory_human || "n/a");

function healthFromGroup(g: any): "good" | "warn" | "bad" {
  const pending = Number(g?.pending ?? 0);
  const lag = Number(g?.lag ?? 0);
  if (pending > 0 || lag > 0) return pending > 10000 || lag > 10000 ? "bad" : "warn";
  return "good";
}

async function login() {
  authError.value = null;
  try {
    const t = await mintToken({ sub: sub.value, role: role.value, admin_secret: adminSecret.value });
    setToken(t);
    token.value = t;
    await refresh();
  } catch (e: any) {
    authError.value = e?.message || "login failed";
  }
}

function logout() {
  clearToken();
  token.value = null;
  summary.value = null;
  error.value = null;
}

async function refresh() {
  error.value = null;
  // Only call protected summary endpoint when authenticated.
  if (token.value) {
    try {
      const s = await fetchSummary();
      summary.value = s;
      if (!selectedTopic.value && s.topics.length > 0) selectedTopic.value = s.topics[0].topic;
    } catch (e: any) {
      const msg = e?.message || "failed";
      // If token is missing/expired, reset UI to login state.
      if (msg === "unauthorized") {
        logout();
      } else {
        error.value = msg;
      }
    }
  } else {
    summary.value = null;
  }

  // Compute ingest throughput (events/sec) by parsing /metrics counter deltas.
  try {
    const metricsText = await fetchMetricsText();
    const total = parseCounter(metricsText, "openstream_ingest_events_total");
    const now = Date.now();
    if (lastIngestTotal != null && lastIngestTs != null) {
      const dt = Math.max(1, (now - lastIngestTs) / 1000);
      ingestRateEps.value = (total - lastIngestTotal) / dt;
    }
    lastIngestTotal = total;
    lastIngestTs = now;
  } catch {
    // ignore
  }
}

let timer: number | null = null;
onMounted(async () => {
  if (token.value) await refresh();
  timer = window.setInterval(refresh, 3000);
});
onUnmounted(() => {
  if (timer) window.clearInterval(timer);
});
</script>

<template>
  <div class="container">
    <div class="topbar">
      <div class="brand">
        <h1>OpenStream Dashboard</h1>
        <div class="sub">Redis Streams · FastAPI · Prometheus/Grafana</div>
      </div>
      <div class="row">
        <span class="pill">API: {{ cfg.apiBaseUrl }}</span>
        <a class="pill" :href="cfg.grafanaUrl" target="_blank" rel="noreferrer">Grafana ↗</a>
        <a class="pill" :href="cfg.prometheusUrl" target="_blank" rel="noreferrer">Prometheus ↗</a>
      </div>
    </div>

    <div v-if="!token" class="card" style="margin-top: 14px">
      <h3>Auth</h3>
      <div class="row" style="gap: 12px">
        <input v-model="sub" placeholder="subject" />
        <select v-model="role">
          <option value="admin">admin</option>
          <option value="producer">producer</option>
          <option value="consumer">consumer</option>
        </select>
        <input v-model="adminSecret" type="password" placeholder="AUTH_ADMIN_SECRET" />
        <button @click="login">Mint token</button>
      </div>
      <div class="hint">
        This is a dev-only flow. In docker-compose defaults, <code>AUTH_ADMIN_SECRET</code> is <code>dev-admin-secret</code>.
        In production you'd use OIDC/SSO and remove the token-mint endpoint.
      </div>
      <div v-if="authError" class="hint" style="color: var(--bad)">{{ authError }}</div>
    </div>

    <div v-else class="row" style="margin-top: 14px; justify-content: space-between">
      <div class="row">
        <span class="badge"><span class="dot good"></span> authenticated</span>
        <button class="secondary" @click="logout">Logout</button>
      </div>
      <div class="row">
        <button class="secondary" @click="refresh">Refresh now</button>
      </div>
    </div>

    <div class="grid">
      <div class="card" style="grid-column: span 4">
        <h3>Event throughput</h3>
        <div class="metric">{{ ingestRateEps == null ? "—" : ingestRateEps.toFixed(1) }}</div>
        <div class="hint">events/sec (computed from Prometheus-format counter deltas)</div>
      </div>

      <div class="card" style="grid-column: span 4">
        <h3>Redis memory</h3>
        <div class="metric">{{ redisMem }}</div>
        <div class="hint">from Redis INFO memory</div>
      </div>

      <div class="card" style="grid-column: span 4">
        <h3>Topics</h3>
        <div class="metric">{{ topics.length }}</div>
        <div class="hint">discovered from ingestion</div>
      </div>

      <div class="card" style="grid-column: span 12">
        <h3>Topic view</h3>
        <div class="row" style="justify-content: space-between">
          <div class="row">
            <select v-model="selectedTopic">
              <option v-for="t in topics" :key="t.topic" :value="t.topic">{{ t.topic }}</option>
            </select>
            <span class="pill" v-if="topic">partitions: {{ topic.partitions }}</span>
          </div>
          <div class="row">
            <span class="pill">Retention: stream length cap (backpressure)</span>
          </div>
        </div>

        <div v-if="error" class="hint" style="color: var(--bad); margin-top: 10px">
          {{ error }} (make sure you have a token and CORS is enabled)
        </div>

        <div v-if="topic" style="margin-top: 12px">
          <table>
            <thead>
              <tr>
                <th>Partition</th>
                <th>Stream length</th>
                <th>Consumer groups</th>
                <th>Lag</th>
                <th>Pending</th>
                <th>Status</th>
              </tr>
            </thead>
            <tbody>
              <tr v-for="p in topic.partition_stats" :key="p.partition">
                <td>{{ p.partition }}</td>
                <td>{{ p.length }}</td>
                <td>
                  <span v-if="p.groups.length === 0" class="hint">—</span>
                  <div v-else class="row">
                    <span v-for="g in p.groups" :key="g.name" class="badge">
                      {{ g.name }}
                    </span>
                  </div>
                </td>
                <td>
                  {{
                    p.groups.reduce((acc, g) => acc + Number((g as any).lag ?? 0), 0)
                  }}
                </td>
                <td>
                  {{
                    p.groups.reduce((acc, g) => acc + Number((g as any).pending ?? 0), 0)
                  }}
                </td>
                <td>
                  <span
                    class="badge"
                    :title="'health based on pending/lag'"
                  >
                    <span
                      class="dot"
                      :class="
                        p.groups.some((g) => healthFromGroup(g) === 'bad')
                          ? 'bad'
                          : p.groups.some((g) => healthFromGroup(g) === 'warn')
                            ? 'warn'
                            : 'good'
                      "
                    ></span>
                    {{
                      p.groups.some((g) => healthFromGroup(g) === "bad")
                        ? "degraded"
                        : p.groups.some((g) => healthFromGroup(g) === "warn")
                          ? "warning"
                          : "ok"
                    }}
                  </span>
                </td>
              </tr>
            </tbody>
          </table>
          <div class="hint" style="margin-top: 10px">
            For historical trends, use Grafana dashboards fed by Prometheus (links above). This UI is a real-time snapshot + computed EPS.
          </div>
        </div>
      </div>
    </div>
  </div>
</template>

