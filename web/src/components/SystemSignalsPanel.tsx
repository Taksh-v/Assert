"use client";

import { useCallback, useEffect, useMemo, useState } from "react";
import { Activity, Gauge, RefreshCw, TriangleAlert } from "lucide-react";
import { apiFetch } from "@/lib/auth";

type LayerStatus = "connected" | "offline" | "error" | "unknown" | "degraded";

interface HealthResponse {
  status: LayerStatus | string;
  version?: string;
  layers?: {
    executive?: { status: LayerStatus | string; engine?: string };
    attention?: { status: LayerStatus | string; engine?: string };
    memory?: { status: LayerStatus | string; engine?: string };
    cache?: { status: LayerStatus | string; engine?: string };
  };
}

interface MetricSample {
  name: string;
  labels: string;
  value: string;
}

function labelForStatus(status?: string) {
  switch (status) {
    case "connected":
      return "connected";
    case "degraded":
      return "degraded";
    case "offline":
      return "offline";
    case "error":
      return "error";
    default:
      return "unknown";
  }
}

function parsePrometheusSamples(text: string): MetricSample[] {
  const samples: MetricSample[] = [];
  const lines = text.split("\n");
  for (const line of lines) {
    const trimmed = line.trim();
    if (!trimmed || trimmed.startsWith("#")) continue;
    if (!trimmed.startsWith("assest_")) continue;

    const match = trimmed.match(/^([a-zA-Z_:][a-zA-Z0-9_:]*)(\{[^}]*\})?\s+(.+)$/);
    if (!match) continue;

    samples.push({
      name: match[1],
      labels: match[2] || "",
      value: match[3],
    });

    if (samples.length >= 4) break;
  }
  return samples;
}

export default function SystemSignalsPanel() {
  const [health, setHealth] = useState<HealthResponse | null>(null);
  const [healthLoading, setHealthLoading] = useState(true);
  const [healthError, setHealthError] = useState<string | null>(null);
  const [metricsText, setMetricsText] = useState<string>("");
  const [metricsLoading, setMetricsLoading] = useState(true);
  const [metricsError, setMetricsError] = useState<string | null>(null);

  const loadSignals = useCallback(async () => {
    setHealthLoading(true);
    setMetricsLoading(true);
    setHealthError(null);
    setMetricsError(null);

    try {
      const healthResponse = await apiFetch("/api/health");
      if (healthResponse.ok) {
        setHealth((await healthResponse.json()) as HealthResponse);
      } else {
        setHealthError(`Health endpoint returned ${healthResponse.status}`);
      }
    } catch (error) {
      setHealthError(error instanceof Error ? error.message : "Failed to load health");
    } finally {
      setHealthLoading(false);
    }

    try {
      const metricsResponse = await apiFetch("/api/metrics");
      if (metricsResponse.ok) {
        setMetricsText(await metricsResponse.text());
      } else {
        setMetricsError(`Metrics endpoint returned ${metricsResponse.status}`);
      }
    } catch (error) {
      setMetricsError(error instanceof Error ? error.message : "Failed to load metrics");
    } finally {
      setMetricsLoading(false);
    }
  }, []);

  useEffect(() => {
    queueMicrotask(() => void loadSignals());
    const timer = window.setInterval(() => {
      void loadSignals();
    }, 30000);

    return () => window.clearInterval(timer);
  }, [loadSignals]);

  const layerRows = useMemo(() => {
    const layers = health?.layers || {};
    return [
      { key: "executive", label: "LLM Path", value: layers.executive?.status || "unknown", engine: layers.executive?.engine || "Gateway" },
      { key: "attention", label: "Vector DB", value: layers.attention?.status || "unknown", engine: layers.attention?.engine || "Qdrant" },
      { key: "memory", label: "Metadata DB", value: layers.memory?.status || "unknown", engine: layers.memory?.engine || "SQL" },
      { key: "cache", label: "Semantic Cache", value: layers.cache?.status || "unknown", engine: layers.cache?.engine || "Redis" },
    ];
  }, [health]);

  const metricSamples = useMemo(() => parsePrometheusSamples(metricsText), [metricsText]);

  const getStatusClass = (status?: string) => {
    const normalized = labelForStatus(status);
    if (normalized === "connected") {
      return "border-[var(--success-muted)] bg-[var(--success-muted)] text-[var(--success)]";
    }
    if (normalized === "degraded") {
      return "border-[var(--warning-muted)] bg-[var(--warning-muted)] text-[var(--warning)]";
    }
    if (normalized === "offline" || normalized === "error") {
      return "border-[var(--danger-muted)] bg-[var(--danger-muted)] text-[var(--danger)]";
    }
    return "border-[var(--border-subtle)] bg-white/[0.7] text-[var(--text-secondary)]";
  };

  return (
    <section className="space-y-4">
      <div className="flex items-center justify-between gap-2 border-b border-[var(--border-subtle)] pb-2">
        <span className="text-[12px] font-semibold text-[var(--text-muted)] tracking-wider uppercase">System Signals</span>
        <button
          onClick={() => void loadSignals()}
          className="flex items-center gap-1.5 rounded-lg border border-[var(--border-subtle)] bg-[var(--bg-surface-hover)] px-2.5 py-1 text-[11px] font-semibold text-[var(--text-secondary)] hover:text-[var(--text-primary)] hover:border-[var(--accent)]/20 transition-colors shadow-sm"
        >
          <RefreshCw className="h-3 w-3" />
          <span>Refresh</span>
        </button>
      </div>

      <div className="space-y-4">
        <div className="flex items-start justify-between gap-3">
          <div>
            <p className="text-sm font-semibold text-[var(--text-primary)] capitalize">{health?.status || "Loading Status"}</p>
            <p className="text-xs text-[var(--text-muted)] mt-0.5">Backend health and metrics snapshot</p>
          </div>
          <div className={`flex items-center gap-1.5 rounded-full border px-2.5 py-0.5 text-[11px] font-semibold ${getStatusClass(health?.status as string)}`}>
            <Activity className="h-3 w-3" />
            <span>{healthLoading ? "Checking" : health?.version || "v?"}</span>
          </div>
        </div>

        {(healthError || metricsError) && (
          <div className="rounded-xl border border-[var(--warning-muted)] bg-[var(--warning-muted)] p-3 text-xs text-[var(--warning)] flex gap-2">
            <TriangleAlert className="h-4 w-4 shrink-0 mt-0.5" />
            <span>{healthError || metricsError}</span>
          </div>
        )}

        <div className="grid grid-cols-2 gap-2">
          {layerRows.map((layer) => {
            const statusVal = labelForStatus(layer.value as string);
            return (
              <div key={layer.key} className="rounded-xl border border-[var(--border-subtle)] bg-[var(--bg-surface-hover)] p-2.5 space-y-2">
                <div className="flex items-center justify-between gap-2">
                  <span className="text-[10px] font-semibold text-[var(--text-muted)] tracking-wider uppercase">{layer.label}</span>
                  <span className={`rounded-full border px-1.5 py-0.5 text-[10px] font-bold capitalize ${getStatusClass(layer.value)}`}>
                    {statusVal}
                  </span>
                </div>
                <p className="text-xs font-semibold text-[var(--text-primary)] truncate">{layer.engine}</p>
              </div>
            );
          })}
        </div>

        {/* Prometheus Metrics Section */}
        <div className="space-y-3">
          <div className="flex items-center justify-between gap-2">
            <span className="text-[12px] font-semibold text-[var(--text-muted)] tracking-wider uppercase">Prometheus Samples</span>
            <span className="text-xs text-[var(--text-muted)]">{metricsLoading ? "Loading..." : `${metricSamples.length} active`}</span>
          </div>
          {metricSamples.length === 0 ? (
            <div className="rounded-xl border border-[var(--border-subtle)] bg-[var(--bg-surface-hover)] p-3 text-xs text-[var(--text-muted)] text-center">
              {metricsError || "No active operational telemetry reported."}
            </div>
          ) : (
            <div className="grid grid-cols-2 gap-2">
              {metricSamples.map((sample) => (
                <div key={`${sample.name}${sample.labels}`} className="rounded-xl border border-[var(--border-subtle)] bg-[var(--bg-surface-hover)] p-2.5 flex flex-col justify-between">
                  <div className="flex items-center justify-between gap-2">
                    <span className="text-xs font-semibold text-[var(--text-primary)] truncate" title={sample.name}>{sample.name.replace("assest_", "")}</span>
                    <Gauge className="h-3 w-3 text-[var(--accent)] shrink-0" />
                  </div>
                  {sample.labels && (
                    <p className="text-[11px] text-[var(--text-muted)] font-mono truncate mt-1" title={sample.labels}>
                      {sample.labels}
                    </p>
                  )}
                  <p className="mt-1.5 text-xs font-bold text-[var(--accent)]">{sample.value}</p>
                </div>
              ))}
            </div>
          )}
        </div>

        <div className="rounded-xl border border-[var(--border-subtle)] bg-[var(--bg-surface-hover)] p-3 text-xs text-[var(--text-muted)] leading-relaxed font-normal">
          This panel is the active health monitor seam. It reports live execution signals, cache status, and Prometheus metrics from the running instance.
        </div>
      </div>
    </section>
  );
}
