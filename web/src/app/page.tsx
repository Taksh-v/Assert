"use client";

import { useEffect, useMemo, useState } from "react";
import { useRouter } from "next/navigation";
import {
  Activity,
  AlertCircle,
  CheckCircle2,
  Clock,
  Database,
  Link2,
  Loader2,
  MessageSquare,
  Send,
} from "lucide-react";
import { apiFetch, getActiveWorkspace, getCurrentUser, ensureDefaultWorkspace } from "@/lib/auth";
import { CONVERSATIONS_CHANGE_EVENT } from "@/components/Sidebar";
import SystemSignalsPanel from "@/components/SystemSignalsPanel";
import { parseUTCDate } from "@/lib/date";

interface Connector {
  id: string;
  type: string;
  status: "active" | "paused" | "error";
  last_synced_at?: string;
  latest_sync?: {
    status: "queued" | "running" | "completed" | "completed_with_errors" | "failed" | "cancelled";
    error?: string | null;
  } | null;
}

interface HealthResponse {
  status: string;
  version?: string;
  layers?: Record<string, { status?: string; engine?: string }>;
}

function formatRelativeTime(isoString?: string) {
  if (!isoString) return "Never synced";
  const date = parseUTCDate(isoString);
  if (Number.isNaN(date.getTime())) return "Unknown";

  const diffMs = Date.now() - date.getTime();
  const diffMins = Math.floor(diffMs / 60000);
  if (diffMins < 1) return "Just now";
  if (diffMins < 60) return `${diffMins}m ago`;

  const diffHours = Math.floor(diffMins / 60);
  if (diffHours < 24) return `${diffHours}h ago`;

  return `${Math.floor(diffHours / 24)}d ago`;
}

function statusClass(status?: string) {
  if (status === "active" || status === "connected" || status === "healthy" || status === "completed") {
    return "border-emerald-500/20 bg-emerald-500/5 text-emerald-400";
  }
  if (status === "running" || status === "queued") {
    return "border-blue-500/20 bg-blue-500/5 text-blue-400";
  }
  if (status === "error" || status === "failed" || status === "offline") {
    return "border-red-500/20 bg-red-500/5 text-red-400";
  }
  if (status === "degraded" || status === "completed_with_errors") {
    return "border-amber-500/20 bg-amber-500/5 text-amber-400";
  }
  return "border-white/[0.06] bg-white/[0.02] text-zinc-400";
}

export default function ChatPage() {
  const [input, setInput] = useState("");
  const [isLoading, setIsLoading] = useState(false);
  const [connectors, setConnectors] = useState<Connector[]>([]);
  const [health, setHealth] = useState<HealthResponse | null>(null);
  const [dashboardLoading, setDashboardLoading] = useState(true);
  const [dashboardError, setDashboardError] = useState<string | null>(null);
  const router = useRouter();

  const user = getCurrentUser();
  const activeWorkspace = getActiveWorkspace();
  const userName = user?.full_name || user?.email?.split("@")[0] || "there";

  useEffect(() => {
    let cancelled = false;

    async function loadDashboard() {
      // PHASE 9: Auto-select workspace if none active
      const currentWs = await ensureDefaultWorkspace();
      
      if (!currentWs?.id) {
        setDashboardLoading(false);
        return;
      }

      setDashboardLoading(true);
      setDashboardError(null);

      try {
        const [connectorsResponse, healthResponse] = await Promise.all([
          apiFetch(`/api/connectors?workspace_id=${currentWs.id}`),
          apiFetch("/api/health"),
        ]);

        if (!connectorsResponse.ok) {
          throw new Error(`Connectors endpoint returned ${connectorsResponse.status}`);
        }

        const nextConnectors = (await connectorsResponse.json()) as Connector[];
        const nextHealth = healthResponse.ok ? ((await healthResponse.json()) as HealthResponse) : null;

        if (!cancelled) {
          setConnectors(nextConnectors);
          setHealth(nextHealth);
        }
      } catch (error) {
        if (!cancelled) {
          setDashboardError(error instanceof Error ? error.message : "Failed to load workspace state");
        }
      } finally {
        if (!cancelled) {
          setDashboardLoading(false);
        }
      }
    }

    void loadDashboard();
    return () => {
      cancelled = true;
    };
  }, [activeWorkspace?.id]);

  const connectorStats = useMemo(() => {
    const active = connectors.filter((connector) => connector.status === "active").length;
    const syncing = connectors.filter((connector) => {
      const status = connector.latest_sync?.status;
      return status === "queued" || status === "running";
    }).length;
    const failed = connectors.filter((connector) => {
      const status = connector.latest_sync?.status;
      return connector.status === "error" || status === "failed";
    }).length;
    const latestSync = connectors
      .map((connector) => connector.last_synced_at)
      .filter(Boolean)
      .sort()
      .at(-1);

    return { active, syncing, failed, latestSync };
  }, [connectors]);

  const suggestions = [
    "What changed in the latest synced docs?",
    "Summarize the current workspace sources",
    "Which answers have the strongest citations?",
  ];

  const handleSend = async (customText?: string) => {
    const textToSend = customText || input;
    if (!textToSend.trim() || isLoading || !activeWorkspace?.id) return;

    setIsLoading(true);

    try {
      const response = await apiFetch("/api/conversations", {
        method: "POST",
        body: JSON.stringify({
          workspace_id: activeWorkspace.id,
          title: textToSend.length > 50 ? `${textToSend.slice(0, 50)}...` : textToSend,
        }),
      });

      if (!response.ok) {
        throw new Error("Failed to create conversation thread.");
      }

      const data = await response.json();
      sessionStorage.setItem("assest_pending_query", textToSend);
      window.dispatchEvent(new Event(CONVERSATIONS_CHANGE_EVENT));
      router.push(`/chat/${data.id}`);
    } catch (error) {
      console.error("Error starting new conversation:", error);
      setIsLoading(false);
    }
  };

  return (
    <div className="flex h-full bg-[#08090d] text-foreground font-sans relative overflow-hidden flex-col xl:flex-row">
      <div className="flex-1 overflow-y-auto p-5 md:p-8 space-y-6 pb-20 scrollbar-thin relative z-10">
        <div className="flex flex-col gap-3 md:flex-row md:items-end md:justify-between">
          <div>
            <span className="text-[9px] font-black uppercase tracking-widest text-primary block mb-1">
              Workspace
            </span>
            <h1 className="text-2xl font-bold text-white tracking-tight">
              Welcome back, <span className="text-primary">{userName}</span>
            </h1>
            <p className="mt-1 text-xs text-zinc-500">
              {activeWorkspace?.name || "Select a workspace to start asking grounded questions."}
            </p>
          </div>

          <div className={`inline-flex w-fit items-center gap-2 rounded-full border px-3 py-1.5 text-[10px] font-black uppercase tracking-widest ${statusClass(health?.status)}`}>
            <Activity className="h-3.5 w-3.5" />
            {health?.status || (dashboardLoading ? "Checking backend" : "Status unavailable")}
          </div>
        </div>

        {dashboardError && (
          <div className="flex items-center gap-2 rounded-xl border border-amber-500/20 bg-amber-500/5 p-3 text-xs text-amber-300">
            <AlertCircle className="h-4 w-4 shrink-0" />
            <span>{dashboardError}</span>
          </div>
        )}

        <div className="grid grid-cols-1 md:grid-cols-4 gap-3">
          <div className="rounded-xl border border-white/[0.04] bg-[#0d0d12]/70 p-4 space-y-1">
            <span className="text-[8px] font-black uppercase tracking-widest text-zinc-500">Connected Sources</span>
            <div className="flex items-baseline gap-2">
              <span className="text-xl font-bold text-white">{dashboardLoading ? "-" : connectorStats.active}</span>
              <span className="text-[9px] text-zinc-500 font-bold">of {connectors.length}</span>
            </div>
          </div>

          <div className="rounded-xl border border-white/[0.04] bg-[#0d0d12]/70 p-4 space-y-1">
            <span className="text-[8px] font-black uppercase tracking-widest text-zinc-500">Syncs Running</span>
            <div className="flex items-baseline gap-2">
              <span className="text-xl font-bold text-white">{dashboardLoading ? "-" : connectorStats.syncing}</span>
              {connectorStats.syncing > 0 && <span className="text-[9px] text-blue-400 font-bold">active</span>}
            </div>
          </div>

          <div className="rounded-xl border border-white/[0.04] bg-[#0d0d12]/70 p-4 space-y-1">
            <span className="text-[8px] font-black uppercase tracking-widest text-zinc-500">Attention Needed</span>
            <div className="flex items-baseline gap-2">
              <span className="text-xl font-bold text-white">{dashboardLoading ? "-" : connectorStats.failed}</span>
              {connectorStats.failed > 0 && <span className="text-[9px] text-red-400 font-bold">check sources</span>}
            </div>
          </div>

          <div className="rounded-xl border border-white/[0.04] bg-[#0d0d12]/70 p-4 space-y-1">
            <span className="text-[8px] font-black uppercase tracking-widest text-zinc-500">Last Sync</span>
            <div className="flex items-center gap-2">
              <Clock className="h-3.5 w-3.5 text-zinc-500" />
              <span className="text-sm font-bold text-white">{dashboardLoading ? "Loading" : formatRelativeTime(connectorStats.latestSync)}</span>
            </div>
          </div>
        </div>

        <div className="rounded-2xl border border-white/[0.04] bg-[#0c0c10]/40 p-5 space-y-4">
          <div className="flex items-center justify-between gap-3">
            <span className="text-[8px] font-black uppercase tracking-widest text-zinc-500">Ask Assest</span>
            {!activeWorkspace?.id && (
              <span className="text-[9px] text-amber-300 font-bold">Workspace required</span>
            )}
          </div>
          <div className="relative flex items-center gap-2 p-2 rounded-xl border border-border bg-[#0e0e13]/80 focus-within:border-zinc-800 transition-all shadow-xl">
            <input
              type="text"
              value={input}
              onChange={(event) => setInput(event.target.value)}
              onKeyDown={(event) => event.key === "Enter" && handleSend()}
              placeholder="Ask a question about connected workspace knowledge..."
              className="flex-1 bg-transparent py-3 px-4 text-xs text-white placeholder-zinc-500 focus:outline-none"
              disabled={isLoading || !activeWorkspace?.id}
            />
            <button
              onClick={() => handleSend()}
              disabled={!input.trim() || isLoading || !activeWorkspace?.id}
              className="h-9 px-4 rounded-lg bg-white hover:bg-primary hover:text-black text-black text-[9px] font-black tracking-widest uppercase flex items-center justify-center gap-1.5 transition-all shrink-0 cursor-pointer disabled:opacity-30 disabled:hover:bg-white disabled:hover:text-black"
            >
              {isLoading ? <Loader2 className="h-3 w-3 animate-spin text-black" /> : <><span>Run</span><Send className="h-3 w-3" /></>}
            </button>
          </div>

          <div className="flex flex-wrap gap-2 pt-1">
            {suggestions.map((question) => (
              <button
                key={question}
                onClick={() => handleSend(question)}
                disabled={isLoading || !activeWorkspace?.id}
                className="px-2.5 py-1 text-[8px] font-black uppercase tracking-wider text-zinc-500 hover:text-white rounded border border-border bg-white/[0.01] hover:bg-white/[0.03] transition-all disabled:opacity-40"
              >
                {question}
              </button>
            ))}
          </div>
        </div>

        <div className="grid grid-cols-1 lg:grid-cols-2 gap-4">
          <div className="rounded-xl border border-white/[0.04] bg-[#0c0c10]/40 p-4 space-y-3">
            <div className="flex items-center justify-between gap-2">
              <span className="text-[8px] font-black uppercase tracking-widest text-zinc-500">Sources</span>
              <Link2 className="h-3.5 w-3.5 text-zinc-500" />
            </div>

            {dashboardLoading ? (
              <div className="text-[9px] font-bold text-zinc-600 uppercase tracking-widest py-8 text-center">
                Loading sources...
              </div>
            ) : connectors.length === 0 ? (
              <div className="rounded-xl border border-dashed border-border p-5 text-center space-y-2">
                <Database className="h-5 w-5 text-zinc-600 mx-auto" />
                <p className="text-[10px] font-black uppercase tracking-widest text-zinc-500">No sources connected</p>
                <button
                  onClick={() => router.push("/connectors")}
                  className="text-[9px] font-black uppercase tracking-widest text-primary hover:text-white"
                >
                  Add a source
                </button>
              </div>
            ) : (
              <div className="space-y-2">
                {connectors.map((connector) => {
                  const syncStatus = connector.latest_sync?.status || connector.status;
                  return (
                    <div key={connector.id} className="flex items-center justify-between gap-3 rounded-lg border border-white/[0.04] bg-white/[0.01] p-3">
                      <div className="min-w-0">
                        <p className="text-[10px] font-bold uppercase tracking-wider text-white truncate">{connector.type.replace("_", " ")}</p>
                        <p className="text-[9px] text-zinc-500">{formatRelativeTime(connector.last_synced_at)}</p>
                      </div>
                      <span className={`rounded-full border px-2 py-1 text-[8px] font-black uppercase tracking-widest ${statusClass(syncStatus)}`}>
                        {syncStatus}
                      </span>
                    </div>
                  );
                })}
              </div>
            )}
          </div>

          <div className="rounded-xl border border-white/[0.04] bg-[#0c0c10]/40 p-4">
            <SystemSignalsPanel />
          </div>
        </div>
      </div>

      <aside className="w-full xl:w-80 border-t xl:border-t-0 xl:border-l border-border p-5 shrink-0 bg-[#09090d]/30 relative z-10">
        <div className="space-y-3">
          <span className="text-[8px] font-black uppercase text-zinc-500 tracking-widest block">Workspace Readiness</span>
          <div className="rounded-xl border border-white/[0.04] bg-[#0c0c10]/40 p-3 space-y-3">
            <div className="flex items-start gap-2">
              <CheckCircle2 className="h-4 w-4 text-emerald-400 shrink-0 mt-0.5" />
              <div>
                <p className="text-[10px] font-bold text-white">Grounded chat</p>
                <p className="text-[9px] text-zinc-500">Answers are generated from the connected workspace and returned citations.</p>
              </div>
            </div>
            <div className="flex items-start gap-2">
              <MessageSquare className="h-4 w-4 text-primary shrink-0 mt-0.5" />
              <div>
                <p className="text-[10px] font-bold text-white">Conversation history</p>
                <p className="text-[9px] text-zinc-500">Threads come from the backend conversation store.</p>
              </div>
            </div>
            <div className="flex items-start gap-2">
              <Activity className="h-4 w-4 text-zinc-500 shrink-0 mt-0.5" />
              <div>
                <p className="text-[10px] font-bold text-white">Live system signals</p>
                <p className="text-[9px] text-zinc-500">Health and Prometheus samples are loaded from the running API.</p>
              </div>
            </div>
          </div>
        </div>
      </aside>
    </div>
  );
}
