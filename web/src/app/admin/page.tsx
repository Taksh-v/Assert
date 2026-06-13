"use client";

import { useEffect, useMemo, useState } from "react";
import { AlertTriangle, BarChart3, Clock3, Database, ShieldCheck, Sparkles, Brain } from "lucide-react";
import SystemSignalsPanel from "@/components/SystemSignalsPanel";
import { apiFetch, ensureDefaultWorkspace, getActiveWorkspace, isAdminWorkspaceRole, AUTH_CHANGE_EVENT } from "@/lib/auth";
import { parseUTCDate } from "@/lib/date";

interface TraceItem {
  id: string;
  question: string;
  answer_preview?: string | null;
  request_id?: string | null;
  created_at: string;
  response_time_ms?: number | null;
  faithfulness_score?: number | null;
  relevance_score?: number | null;
  eval_reasoning?: string | null;
  sources_count: number;
}

interface ReasoningRunItem {
  execution_id: string;
  query: string;
  status: string;
  request_id?: string | null;
  created_at: string;
  updated_at: string;
  confidence: number;
  eval_count: number;
  flagged_for_review: boolean;
  iterations: number;
}

interface ObservabilityOverview {
  workspace_id: string;
  query_count: number;
  avg_response_time_ms: number;
  avg_faithfulness: number;
  avg_relevance: number;
  low_confidence_count: number;
  recent_queries: TraceItem[];
  recent_reasoning_runs: ReasoningRunItem[];
}

interface HealthResponse {
  status: string;
  version?: string;
  layers?: Record<string, { status?: string; engine?: string }>;
}

function scoreLabel(score?: number | null) {
  if (score === undefined || score === null) return "n/a";
  return `${Math.round(score * 100)}%`;
}

function statusClass(status?: string) {
  if (status === "completed" || status === "healthy" || status === "connected") {
    return "border-[var(--success-muted)] bg-[var(--success-muted)] text-[var(--success)]";
  }
  if (status === "running" || status === "queued") {
    return "border-[var(--accent)]/20 bg-[var(--accent-muted)] text-[var(--accent)]";
  }
  if (status === "failed" || status === "error" || status === "offline") {
    return "border-[var(--danger-muted)] bg-[var(--danger-muted)] text-[var(--danger)]";
  }
  if (status === "suspended" || status === "degraded") {
    return "border-[var(--warning-muted)] bg-[var(--warning-muted)] text-[var(--warning)]";
  }
  return "border-[var(--border-subtle)] bg-[var(--bg-surface-hover)] text-[var(--text-secondary)]";
}

export default function AdminPage() {
  const [overview, setOverview] = useState<ObservabilityOverview | null>(null);
  const [health, setHealth] = useState<HealthResponse | null>(null);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);
  const [workspace, setWorkspace] = useState(getActiveWorkspace());
  const isAdmin = isAdminWorkspaceRole(workspace?.role);

  useEffect(() => {
    const handleAuthChange = () => {
      setWorkspace(getActiveWorkspace());
    };
    window.addEventListener(AUTH_CHANGE_EVENT, handleAuthChange);
    return () => window.removeEventListener(AUTH_CHANGE_EVENT, handleAuthChange);
  }, []);

  useEffect(() => {
    let cancelled = false;

    async function loadAdminData() {
      setLoading(true);
      setError(null);

      try {
        const currentWorkspace = await ensureDefaultWorkspace();
        if (!currentWorkspace?.id) {
          if (!cancelled) {
            setOverview(null);
            setHealth(null);
            setError("No workspace is available for this account.");
          }
          return;
        }

        const [overviewRes, healthRes] = await Promise.all([
          apiFetch(`/api/observability/overview?workspace_id=${currentWorkspace.id}`),
          apiFetch("/api/health"),
        ]);

        if (!overviewRes.ok) {
          throw new Error(`Observability endpoint returned ${overviewRes.status}`);
        }

        const nextOverview = (await overviewRes.json()) as ObservabilityOverview;
        const nextHealth = healthRes.ok ? ((await healthRes.json()) as HealthResponse) : null;

        if (!cancelled) {
          setOverview(nextOverview);
          setHealth(nextHealth);
        }
      } catch (err) {
        if (!cancelled) {
          setError(err instanceof Error ? err.message : "Failed to load admin telemetry");
        }
      } finally {
        if (!cancelled) {
          setLoading(false);
        }
      }
    }

    void loadAdminData();
    return () => {
      cancelled = true;
    };
  }, []);

  const healthState = useMemo(() => {
    return health?.status || "unknown";
  }, [health]);

  if (loading && !workspace?.role) {
    return (
      <div className="flex min-h-full items-center justify-center p-6 bg-[var(--bg-root)]">
        <div className="glass-panel px-5 py-4 text-xs font-mono text-[var(--text-secondary)]">
          INITIALIZING TELEMETRY CONSOLE...
        </div>
      </div>
    );
  }

  if (!isAdmin) {
    return (
      <div className="flex min-h-full items-center justify-center p-6 bg-[var(--bg-root)]">
        <div className="max-w-md glass-panel p-6">
          <div className="mb-4 flex h-12 w-12 items-center justify-center rounded bg-[var(--accent-muted)] border border-[var(--accent)]/10">
            <ShieldCheck className="h-5 w-5 text-[var(--accent)]" />
          </div>
          <h1 className="text-lg font-bold text-[var(--text-primary)] uppercase tracking-wide">Admin access required</h1>
          <p className="mt-2 text-xs text-[var(--text-secondary)] leading-relaxed font-medium">
            This console is reserved for workspace owners and admins. The user experience stays focused on chat and sources, while traces, health, and evals live here.
          </p>
        </div>
      </div>
    );
  }

  const kpis = [
    { label: "Queries", value: loading ? "-" : overview?.query_count ?? 0, icon: BarChart3 },
    { label: "Avg faithfulness", value: loading ? "-" : scoreLabel(overview?.avg_faithfulness), icon: Sparkles },
    { label: "Avg relevance", value: loading ? "-" : scoreLabel(overview?.avg_relevance), icon: Brain },
    { label: "Low confidence", value: loading ? "-" : overview?.low_confidence_count ?? 0, icon: AlertTriangle },
  ];

  return (
    <div className="relative h-full overflow-y-auto bg-[var(--bg-root)] text-[var(--text-primary)] animate-fade-in">
      <div className="absolute left-0 top-0 h-[380px] w-[380px] rounded-full bg-[var(--accent)]/5 blur-[120px] pointer-events-none" />
      <div className="absolute right-0 top-20 h-[320px] w-[320px] rounded-full bg-[var(--warning)]/4 blur-[120px] pointer-events-none" />

      <div className="p-6 md:p-10 space-y-6">
        <div className="flex flex-col gap-4 lg:flex-row lg:items-end lg:justify-between">
          <div className="space-y-1.5">
            <span className="label-caps text-[10px] text-[var(--text-muted)]">Admin console</span>
            <h1 className="text-2xl md:text-3xl font-extrabold tracking-tight text-[var(--text-primary)] font-display">Interpretability and operations</h1>
            <p className="max-w-2xl text-xs text-[var(--text-secondary)] font-medium leading-relaxed">
              Review backend traces, evaluation results, and live system health without exposing operational noise to end users.
            </p>
          </div>
          <div className={`inline-flex items-center gap-2 rounded-full border px-3.5 py-1 text-[11px] font-semibold ${statusClass(healthState)}`}>
            <span className="relative flex h-2 w-2">
              <span className={`animate-ping absolute inline-flex h-full w-full rounded-full opacity-75 ${health?.status === "healthy" ? "bg-[var(--success)]" : "bg-[var(--warning)]"}`}></span>
              <span className={`relative inline-flex rounded-full h-2 w-2 ${health?.status === "healthy" ? "bg-[var(--success)]" : "bg-[var(--warning)]"}`}></span>
            </span>
            <span className="font-mono uppercase tracking-wide">{health?.status || (loading ? "Checking health" : "Status unavailable")}</span>
            {health?.version && <span className="font-mono text-[10px] text-[var(--text-muted)] ml-1">V{health.version}</span>}
          </div>
        </div>

        {error && (
          <div className="flex items-center gap-2 rounded-lg border border-[var(--danger)]/25 bg-[var(--danger-muted)] px-4 py-3 text-xs font-semibold text-[var(--danger)]">
            <AlertTriangle className="h-4 w-4 shrink-0 text-[var(--danger)]" />
            <span>{error}</span>
          </div>
        )}

        <div className="grid grid-cols-1 gap-4 md:grid-cols-2 xl:grid-cols-4">
          {kpis.map((card) => {
            const Icon = card.icon;
            return (
              <div key={card.label} className="glass-panel glass-panel-interactive p-5">
                <div className="flex items-center justify-between gap-3">
                  <span className="label-caps text-[10px] text-[var(--text-secondary)]">{card.label}</span>
                  <Icon className="h-4 w-4 text-[var(--accent)]" />
                </div>
                <div className="mt-3 text-2xl font-bold tracking-tight text-[var(--text-primary)] font-display">{card.value}</div>
              </div>
            );
          })}
        </div>

        <div className="grid gap-6 xl:grid-cols-[1.5fr_1fr]">
          <section className="glass-panel p-6 space-y-5">
            <div className="flex items-center justify-between gap-2 border-b border-[var(--border-subtle)] pb-3">
              <div>
                <h2 className="text-sm font-bold tracking-tight uppercase text-[var(--text-primary)] font-display">Recent traces</h2>
                <p className="text-[10px] font-mono text-[var(--text-muted)] mt-0.5 uppercase tracking-wide">QUERY LOGS WITH EVALUATION SCORERS</p>
              </div>
              <div className="rounded border border-[var(--border-subtle)] bg-[var(--bg-surface)] px-2.5 py-0.5 text-[10px] font-bold font-mono uppercase text-[var(--text-secondary)]">
                {overview?.recent_queries.length || 0} ITEMS
              </div>
            </div>

            <div className="space-y-4">
              {(overview?.recent_queries || []).length === 0 ? (
                <div className="rounded-lg border border-dashed border-[var(--border-subtle)] bg-[var(--bg-surface)] p-6 text-center text-xs text-[var(--text-muted)]">
                  No recent traces found for this workspace.
                </div>
              ) : (
                overview!.recent_queries.map((trace) => (
                  <div key={trace.id} className="rounded-lg border border-[var(--border-subtle)] bg-[var(--bg-surface)] hover:bg-[var(--bg-surface-hover)] p-4 space-y-4 transition-colors">
                    <div className="flex items-start justify-between gap-3">
                      <div className="min-w-0 space-y-1.5">
                        <p className="text-sm font-semibold text-[var(--text-primary)] overflow-hidden text-ellipsis whitespace-normal">{trace.question}</p>
                        <div className="flex flex-wrap items-center gap-2 text-[10px] font-mono text-[var(--text-muted)]">
                          <span className="rounded border border-[var(--border-subtle)] px-2 py-0.5">{trace.request_id || "no request id"}</span>
                          <span>{parseUTCDate(trace.created_at).toLocaleString().toUpperCase()}</span>
                        </div>
                      </div>
                      <div className="flex items-center gap-2 shrink-0">
                        {trace.response_time_ms !== undefined && trace.response_time_ms !== null && (
                          <span className="rounded border border-[var(--border-subtle)] bg-[var(--bg-surface)] px-2.5 py-0.5 text-[10px] font-bold font-mono text-[var(--text-secondary)]">
                            {trace.response_time_ms} MS
                          </span>
                        )}
                        <span className={`rounded border px-2.5 py-0.5 text-[10px] font-bold tracking-wide uppercase ${statusClass((trace.faithfulness_score ?? 1) < 0.5 ? "failed" : "completed")}`}>
                          {trace.sources_count} SOURCE{trace.sources_count === 1 ? "" : "S"}
                        </span>
                      </div>
                    </div>

                    <div className="grid grid-cols-1 gap-3 sm:grid-cols-3">
                      <div className="rounded border border-[var(--border-subtle)] bg-[var(--bg-surface-hover)]/30 p-3">
                        <p className="label-caps text-[9px] text-[var(--text-muted)]">Faithfulness</p>
                        <p className="mt-1 text-sm font-bold text-[var(--text-primary)] font-mono">{scoreLabel(trace.faithfulness_score)}</p>
                      </div>
                      <div className="rounded border border-[var(--border-subtle)] bg-[var(--bg-surface-hover)]/30 p-3">
                        <p className="label-caps text-[9px] text-[var(--text-muted)]">Relevance</p>
                        <p className="mt-1 text-sm font-bold text-[var(--text-primary)] font-mono">{scoreLabel(trace.relevance_score)}</p>
                      </div>
                      <div className="rounded border border-[var(--border-subtle)] bg-[var(--bg-surface-hover)]/30 p-3">
                        <p className="label-caps text-[9px] text-[var(--text-muted)]">Answer preview</p>
                        <p className="mt-1 text-[11px] text-[var(--text-secondary)] truncate leading-relaxed font-medium">{trace.answer_preview || "No answer preview available."}</p>
                      </div>
                    </div>

                    {trace.eval_reasoning && (
                      <div className="rounded border border-[var(--border-subtle)] bg-[var(--bg-surface-hover)]/30 p-3 text-xs leading-relaxed text-[var(--text-secondary)] font-medium font-mono">
                        {trace.eval_reasoning}
                      </div>
                    )}
                  </div>
                ))
              )}
            </div>
          </section>

          <section className="space-y-6">
            <div className="glass-panel p-6 space-y-5">
              <div className="flex items-center justify-between gap-2 border-b border-[var(--border-subtle)] pb-3">
                <div>
                  <h2 className="text-sm font-bold tracking-tight uppercase text-[var(--text-primary)] font-display">Reasoning runs</h2>
                  <p className="text-[10px] font-mono text-[var(--text-muted)] mt-0.5 uppercase tracking-wide">DURABLE WORKFLOW AGENTS</p>
                </div>
                <Database className="h-4 w-4 text-[var(--text-muted)]" />
              </div>

              <div className="space-y-4">
                {(overview?.recent_reasoning_runs || []).length === 0 ? (
                  <div className="rounded-lg border border-dashed border-[var(--border-subtle)] bg-[var(--bg-surface)] p-6 text-center text-xs text-[var(--text-muted)]">
                    No reasoning runs recorded yet.
                  </div>
                ) : (
                  overview!.recent_reasoning_runs.map((run) => (
                    <div key={run.execution_id} className="rounded-lg border border-[var(--border-subtle)] bg-[var(--bg-surface)] hover:bg-[var(--bg-surface-hover)] p-4 space-y-4 transition-colors">
                      <div className="flex items-start justify-between gap-3">
                        <div className="min-w-0">
                          <p className="text-sm font-semibold text-[var(--text-primary)] overflow-hidden text-ellipsis whitespace-normal">{run.query}</p>
                          <div className="mt-1.5 flex flex-wrap items-center gap-2 text-[10px] font-mono text-[var(--text-muted)]">
                            <span className="rounded border border-[var(--border-subtle)] px-2 py-0.5">{run.execution_id.slice(0, 8).toUpperCase()}</span>
                            <span>{parseUTCDate(run.updated_at).toLocaleString().toUpperCase()}</span>
                          </div>
                        </div>
                        <span className={`rounded border px-2.5 py-0.5 text-[10px] font-bold tracking-wider uppercase font-mono ${statusClass(run.status)}`}>
                          {run.status}
                        </span>
                      </div>

                      <div className="grid grid-cols-3 gap-2">
                        <div className="rounded border border-[var(--border-subtle)] bg-[var(--bg-surface-hover)]/30 p-3">
                          <p className="label-caps text-[9px] text-[var(--text-muted)]">Confidence</p>
                          <p className="mt-1 text-sm font-bold text-[var(--text-primary)] font-mono">{scoreLabel(run.confidence)}</p>
                        </div>
                        <div className="rounded border border-[var(--border-subtle)] bg-[var(--bg-surface-hover)]/30 p-3">
                          <p className="label-caps text-[9px] text-[var(--text-muted)]">Evals</p>
                          <p className="mt-1 text-sm font-bold text-[var(--text-primary)] font-mono">{run.eval_count}</p>
                        </div>
                        <div className="rounded border border-[var(--border-subtle)] bg-[var(--bg-surface-hover)]/30 p-3">
                          <p className="label-caps text-[9px] text-[var(--text-muted)]">Iterations</p>
                          <p className="mt-1 text-sm font-bold text-[var(--text-primary)] font-mono">{run.iterations}</p>
                        </div>
                      </div>

                      {run.flagged_for_review && (
                        <div className="flex items-center gap-2 rounded-lg border border-[var(--warning)]/20 bg-[var(--warning-muted)] px-3 py-2 text-xs font-semibold text-[var(--warning)]">
                          <AlertTriangle className="h-3.5 w-3.5 shrink-0" />
                          <span>Flagged for review</span>
                        </div>
                      )}
                    </div>
                  ))
                )}
              </div>
            </div>

            <div className="glass-panel p-6">
              <SystemSignalsPanel />
            </div>

            <div className="glass-panel p-6">
              <div className="flex items-start gap-3">
                <Clock3 className="mt-0.5 h-4.5 w-4.5 text-[var(--accent)] shrink-0" />
                <div>
                  <p className="text-xs font-bold text-[var(--text-primary)] uppercase tracking-wide">Operation Isolation Standards</p>
                  <p className="mt-1.5 text-xs text-[var(--text-secondary)] font-medium leading-relaxed">
                    End users should only see citations, grounding, and the action they need next. Deep traces, infra health, and eval histories belong here so the customer-facing flow stays calm and focused.
                  </p>
                </div>
              </div>
            </div>
          </section>
        </div>
      </div>
    </div>
  );
}
