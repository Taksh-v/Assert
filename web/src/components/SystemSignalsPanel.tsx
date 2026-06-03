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
            { key: "executive", label: "LLM", value: layers.executive?.status || "unknown", engine: layers.executive?.engine || "Gateway" },
            { key: "attention", label: "Vector", value: layers.attention?.status || "unknown", engine: layers.attention?.engine || "Qdrant" },
            { key: "memory", label: "DB", value: layers.memory?.status || "unknown", engine: layers.memory?.engine || "SQL" },
            { key: "cache", label: "Cache", value: layers.cache?.status || "unknown", engine: layers.cache?.engine || "Redis" },
        ];
    }, [health]);

    const metricSamples = useMemo(() => parsePrometheusSamples(metricsText), [metricsText]);

    return (
        <section className="space-y-2">
            <div className="flex items-center justify-between gap-2">
                <span className="text-[9px] font-black uppercase text-zinc-500 tracking-widest">System Signals</span>
                <button
                    onClick={() => void loadSignals()}
                    className="flex items-center gap-1.5 rounded-full border border-white/[0.05] bg-white/[0.02] px-2.5 py-1 text-[9px] font-black uppercase tracking-widest text-zinc-400 hover:text-white hover:border-primary/30 transition-colors"
                >
                    <RefreshCw className="h-3 w-3" />
                    Refresh
                </button>
            </div>

            <div className="rounded-2xl border border-white/[0.04] bg-white/[0.01] p-3 space-y-3">
                <div className="flex items-start justify-between gap-2">
                    <div>
                        <p className="text-[10px] font-black uppercase tracking-wider text-white">{health?.status || "loading"}</p>
                        <p className="text-[9px] text-zinc-500 mt-0.5">Backend health and metrics snapshot</p>
                    </div>
                    <div className={`flex items-center gap-1.5 rounded-full border px-2 py-1 text-[9px] font-black uppercase tracking-widest ${labelForStatus(health?.status as string) === "connected" ? "border-emerald-500/20 bg-emerald-500/5 text-emerald-400" : labelForStatus(health?.status as string) === "degraded" ? "border-amber-500/20 bg-amber-500/5 text-amber-400" : "border-white/[0.06] bg-white/[0.02] text-zinc-400"}`}>
                        <Activity className="h-3 w-3" />
                        {healthLoading ? "Checking" : health?.version || "v?"}
                    </div>
                </div>

                {(healthError || metricsError) && (
                    <div className="rounded-xl border border-amber-500/20 bg-amber-500/5 p-2.5 text-[10px] text-amber-300 flex gap-2">
                        <TriangleAlert className="h-3.5 w-3.5 shrink-0 mt-0.5" />
                        <span>{healthError || metricsError}</span>
                    </div>
                )}

                <div className="grid grid-cols-2 gap-2">
                    {layerRows.map((layer) => {
                        const status = labelForStatus(layer.value as string);
                        const statusClasses =
                            status === "connected"
                                ? "border-emerald-500/20 bg-emerald-500/5 text-emerald-400"
                                : status === "degraded"
                                    ? "border-amber-500/20 bg-amber-500/5 text-amber-400"
                                    : status === "offline" || status === "error"
                                        ? "border-red-500/20 bg-red-500/5 text-red-400"
                                        : "border-white/[0.06] bg-white/[0.02] text-zinc-400";

                        return (
                            <div key={layer.key} className="rounded-xl border border-white/[0.04] bg-black/20 p-2.5">
                                <div className="flex items-center justify-between gap-2">
                                    <span className="text-[9px] font-black uppercase tracking-widest text-zinc-500">{layer.label}</span>
                                    <span className={`rounded-full border px-1.5 py-0.5 text-[8px] font-black uppercase tracking-widest ${statusClasses}`}>
                                        {status}
                                    </span>
                                </div>
                                <p className="mt-1 text-[10px] font-bold text-white truncate">{layer.engine}</p>
                            </div>
                        );
                    })}
                </div>

                <div className="space-y-2">
                    <div className="flex items-center justify-between gap-2">
                        <span className="text-[9px] font-black uppercase text-zinc-500 tracking-widest">Prometheus Samples</span>
                        <span className="text-[8px] font-black uppercase text-zinc-600 tracking-widest">{metricsLoading ? "loading" : `${metricSamples.length} shown`}</span>
                    </div>
                    {metricSamples.length === 0 ? (
                        <div className="rounded-xl border border-white/[0.04] bg-black/20 p-2.5 text-[10px] text-zinc-500">
                            {metricsError || "No Assest metrics exposed yet."}
                        </div>
                    ) : (
                        <div className="space-y-2">
                            {metricSamples.map((sample) => (
                                <div key={`${sample.name}${sample.labels}`} className="rounded-xl border border-white/[0.04] bg-black/20 p-2.5">
                                    <div className="flex items-center justify-between gap-2">
                                        <span className="text-[10px] font-bold text-white truncate">{sample.name}</span>
                                        <Gauge className="h-3 w-3 text-primary shrink-0" />
                                    </div>
                                    {sample.labels && <p className="mt-1 text-[9px] text-zinc-500 truncate">{sample.labels}</p>}
                                    <p className="mt-1 text-[11px] font-black text-primary">{sample.value}</p>
                                </div>
                            ))}
                        </div>
                    )}
                </div>

                <div className="rounded-xl border border-white/[0.04] bg-black/20 p-2.5 text-[10px] text-zinc-500 leading-relaxed">
                    This panel is the monitoring seam for the workspace. It shows whether the LLM path, vector store, database, cache, and Prometheus export are live.
                </div>
            </div>
        </section>
    );
}
