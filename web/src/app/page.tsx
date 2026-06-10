"use client";

import { useEffect, useMemo, useState, useRef } from "react";
import { useRouter } from "next/navigation";
import {
  ArrowRight,
  Database,
  Loader2,
  Send,
  ShieldCheck,
  Sparkles,
  HeartPulse,
  Cpu,
  Paperclip,
} from "lucide-react";
import { apiFetch, ensureDefaultWorkspace, getActiveWorkspace, getCurrentUser, AUTH_CHANGE_EVENT } from "@/lib/auth";
import { CONVERSATIONS_CHANGE_EVENT } from "@/components/Sidebar";
import { parseUTCDate } from "@/lib/date";
import ConnectorIcon from "@/components/ConnectorIcon";

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
    return "border-emerald-200 bg-emerald-50 text-emerald-700";
  }
  if (status === "running" || status === "queued") {
    return "border-blue-200 bg-blue-50 text-blue-700";
  }
  if (status === "error" || status === "failed" || status === "offline") {
    return "border-rose-200 bg-rose-50 text-rose-700";
  }
  if (status === "degraded" || status === "completed_with_errors") {
    return "border-amber-200 bg-amber-50 text-amber-700";
  }
  return "border-slate-200 bg-white text-slate-500";
}

function getGreeting(name: string) {
  const hr = new Date().getHours();
  let base = "Good night";

  if (hr >= 5 && hr < 12) base = "Good morning";
  else if (hr >= 12 && hr < 17) base = "Good afternoon";
  else if (hr >= 17 && hr < 21) base = "Good evening";

  return (
    <h1 className="text-2xl font-bold tracking-tight text-[var(--text-primary)] sm:text-3xl font-display">
      {base}{name ? `, ${name}` : ""}
    </h1>
  );
}

export default function ChatPage() {
  const [input, setInput] = useState("");
  const [isLoading, setIsLoading] = useState(false);
  const [isUploading, setIsUploading] = useState(false);
  const [uploadStatus, setUploadStatus] = useState<{ success: boolean; message: string } | null>(null);
  const [connectors, setConnectors] = useState<Connector[]>([]);
  const [health, setHealth] = useState<HealthResponse | null>(null);
  const [dashboardLoading, setDashboardLoading] = useState(true);
  const [user, setUser] = useState(getCurrentUser());
  const router = useRouter();
  const fileInputRef = useRef<HTMLInputElement>(null);

  const activeWorkspace = getActiveWorkspace();

  const handleFileUpload = async (event: React.ChangeEvent<HTMLInputElement>) => {
    const file = event.target.files?.[0];
    if (!file || !activeWorkspace?.id) return;

    setIsUploading(true);
    setUploadStatus(null);

    const formData = new FormData();
    formData.append("file", file);
    formData.append("workspace_id", activeWorkspace.id);

    try {
      const response = await apiFetch("/api/documents/upload", {
        method: "POST",
        body: formData,
      });

      if (!response.ok) {
        throw new Error("Failed to upload document");
      }

      setUploadStatus({ success: true, message: "Document uploaded and ingested successfully!" });
      
      // Auto-clear success message after 5 seconds
      setTimeout(() => setUploadStatus(null), 5000);
      
      // Refresh connectors to show new document count if needed
      const connectorsResponse = await apiFetch(`/api/connectors?workspace_id=${activeWorkspace.id}`);
      if (connectorsResponse.ok) {
        setConnectors(await connectorsResponse.json() as Connector[]);
      }
    } catch (error) {
      console.error("Upload error:", error);
      setUploadStatus({ success: false, message: error instanceof Error ? error.message : "Failed to upload document" });
    } finally {
      setIsUploading(false);
      if (fileInputRef.current) fileInputRef.current.value = "";
    }
  };
  const userName = user?.full_name || user?.email?.split("@")[0] || "";
  const workspaceName = activeWorkspace?.name || "your workspace";

  useEffect(() => {
    const handleAuthChange = () => setUser(getCurrentUser());
    window.addEventListener(AUTH_CHANGE_EVENT, handleAuthChange);

    let cancelled = false;

    async function loadDashboard() {
      // Don't await if we already have it in localStorage
      const currentWs = getActiveWorkspace() || await ensureDefaultWorkspace();

      if (!currentWs?.id) {
        setDashboardLoading(false);
        return;
      }

      // If we have existing data, don't show full-page loader
      if (connectors.length === 0) {
        setDashboardLoading(true);
      }

      try {
        const [connectorsResponse, healthResponse] = await Promise.all([
          apiFetch(`/api/connectors?workspace_id=${currentWs.id}`),
          apiFetch("/api/health"),
        ]);

        const [nextConnectors, nextHealth] = await Promise.all([
          connectorsResponse.ok ? connectorsResponse.json() : Promise.resolve([]),
          healthResponse.ok ? healthResponse.json() : Promise.resolve(null)
        ]);

        if (!cancelled) {
          setConnectors(nextConnectors as Connector[]);
          setHealth(nextHealth as HealthResponse);
        }
      } catch (error) {
        if (!cancelled) {
          console.error(error instanceof Error ? error.message : "Failed to load workspace state");
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
      window.removeEventListener(AUTH_CHANGE_EVENT, handleAuthChange);
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
    { text: "What changed in the latest synced docs?", category: "Review" },
    { text: "Summarize the current workspace sources.", category: "Overview" },
    { text: "Which answers have the strongest citations?", category: "Verify" },
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

  const handleKeyDown = (event: React.KeyboardEvent<HTMLTextAreaElement>) => {
    if (event.key === "Enter" && !event.shiftKey) {
      event.preventDefault();
      void handleSend();
    }
  };

  const healthState = health?.status || (dashboardLoading ? "connecting" : "offline");

  return (
    <div className="relative h-full overflow-y-auto bg-[var(--bg-root)] text-[var(--text-primary)]">
      {/* Premium Ambient Radial Glows */}
      <div className="pointer-events-none absolute left-[-6rem] top-[-6rem] h-96 w-96 rounded-full bg-[var(--accent)]/8 blur-[100px]" />
      <div className="pointer-events-none absolute bottom-[-8rem] right-[-6rem] h-[500px] w-[500px] rounded-full bg-emerald-500/5 blur-[120px]" />

      <div className="mx-auto flex w-full max-w-[1700px] flex-col gap-6 px-4 py-6 sm:px-6 md:py-8 lg:px-8">
        {/* Workspace Header */}
        <header className="flex flex-col gap-4 lg:flex-row lg:items-end lg:justify-between border-b border-[var(--border-subtle)] pb-6">
          <div className="max-w-3xl space-y-3">
            <div className="inline-flex items-center gap-2 rounded-full border border-[var(--border-subtle)] bg-[var(--bg-surface)] px-3 py-1.5 text-[9px] font-bold uppercase tracking-[0.18em] text-[var(--accent)] shadow-[var(--shadow-card)]">
              <Sparkles className="h-3 w-3" />
              Workspace Composer
            </div>
            <div className="space-y-2">
              {getGreeting(userName)}
              <p className="max-w-2xl text-xs text-[var(--text-secondary)] leading-relaxed font-mono uppercase tracking-wide">
                Grounded reasoning and document search within{" "}
                <span className="font-semibold text-[var(--text-primary)]">{workspaceName}</span>.
              </p>
            </div>
          </div>

          <div className="flex flex-wrap items-center gap-3">
            <span className={`inline-flex items-center gap-2 rounded-full border px-3 py-1.5 text-[9px] font-bold uppercase tracking-[0.16em] ${statusClass(healthState)} shadow-sm`}>
              <span className={`h-1.5 w-1.5 rounded-full ${healthState === "healthy" || healthState === "connected" ? "bg-emerald-500 shadow-[0_0_6px_#10b981]" : healthState === "connecting" || healthState === "running" ? "bg-blue-500 shadow-[0_0_6px_#6366f1]" : "bg-amber-500 shadow-[0_0_6px_#f59e0b]"} animate-pulse`} />
              {healthState}
            </span>
            <button
              onClick={() => router.push("/connectors")}
              className="inline-flex items-center gap-2 rounded-full border border-[var(--border-subtle)] bg-[var(--bg-surface)] px-4 py-2 text-[10px] font-bold text-[var(--text-primary)] uppercase tracking-wider shadow-sm transition-all duration-200 hover:border-[var(--border-focus)] hover:bg-[var(--bg-surface-hover)] active:scale-95 cursor-pointer"
            >
              Manage Environment
              <ArrowRight className="h-3.5 w-3.5 text-[var(--accent)]" />
            </button>
          </div>
        </header>

        {/* 3-Column Split-Deck Grid Layout */}
        <div className="grid gap-6 grid-cols-1 md:grid-cols-2 xl:grid-cols-3">

          {/* Column 1: Command Center (Composer + Prompts) */}
          <section className="rounded-2xl border border-[var(--border-subtle)] bg-[var(--bg-surface)] p-5 shadow-[var(--shadow-elevated)] flex flex-col justify-between group/card relative overflow-hidden backdrop-blur-md">
            <div className="absolute inset-0 bg-gradient-to-tr from-indigo-500/2 to-transparent pointer-events-none" />
            <div>
              <div className="flex items-center justify-between border-b border-[var(--border-subtle)] pb-3 mb-5">
                <div>
                  <p className="label-caps font-bold">Composer</p>
                  <h2 className="text-[14px] font-semibold tracking-tight text-[var(--text-primary)] mt-1">Submit Grounded Query</h2>
                </div>
                <ShieldCheck className="h-4 w-4 text-[var(--success)]" />
              </div>

              <div className="rounded-xl border border-[var(--border-subtle)] bg-[var(--bg-root)] p-3.5 shadow-inner focus-within:border-[var(--border-focus)] focus-within:shadow-[var(--shadow-glow)] transition-all duration-250">
                <textarea
                  value={input}
                  onChange={(event) => setInput(event.target.value)}
                  onKeyDown={handleKeyDown}
                  placeholder="Ask a question about connected codebases, docs, files, or Slack discussions..."
                  rows={6}
                  className="composer-textarea min-h-[160px] w-full resize-none border-none bg-transparent text-[13px] leading-relaxed text-slate-200 placeholder:text-[var(--text-muted)] focus:outline-none scrollbar-thin"
                  disabled={isLoading || !activeWorkspace?.id}
                />

                <div className="mt-3 flex flex-wrap items-center justify-between gap-3 border-t border-[var(--border-subtle)]/40 pt-3">
                  <div className="flex flex-wrap items-center gap-1.5">
                    <input
                      type="file"
                      ref={fileInputRef}
                      onChange={handleFileUpload}
                      className="hidden"
                      accept=".pdf,.txt,.docx,.md"
                    />
                    <button
                      onClick={() => fileInputRef.current?.click()}
                      disabled={isUploading || isLoading || !activeWorkspace?.id}
                      title="Upload document"
                      className="flex h-6 w-6 items-center justify-center rounded border border-[var(--border-subtle)] bg-[var(--bg-surface)] text-[var(--text-muted)] hover:border-[var(--border-focus)] hover:bg-[var(--bg-surface-hover)] hover:text-[var(--text-primary)] transition-all disabled:opacity-40 disabled:cursor-not-allowed cursor-pointer"
                    >
                      {isUploading ? (
                        <Loader2 className="h-3 w-3 animate-spin" />
                      ) : (
                        <Paperclip className="h-3.5 w-3.5" />
                      )}
                    </button>
                    <span className="rounded bg-[var(--bg-surface)] border border-[var(--border-subtle)] px-2 py-0.5 text-[8px] font-bold uppercase tracking-wider text-[var(--text-secondary)]">
                      {connectors.length || 0} Grounded Sources
                    </span>
                    <span className="rounded bg-[var(--bg-surface)] border border-[var(--border-subtle)] px-2 py-0.5 text-[8px] font-bold uppercase tracking-wider text-[var(--text-muted)]">
                      ⏎ Send
                    </span>
                  </div>

                  <button
                    onClick={() => handleSend()}
                    disabled={!input.trim() || isLoading || isUploading || !activeWorkspace?.id}
                    className="inline-flex items-center justify-center gap-2 rounded-lg bg-[var(--accent)] px-3.5 py-1.5 text-[10px] font-bold uppercase tracking-wider text-white shadow-[var(--shadow-glow)] transition-all duration-200 hover:bg-[var(--accent-hover)] active:scale-95 disabled:cursor-not-allowed disabled:opacity-40"
                  >
                    {isLoading ? <Loader2 className="h-3 w-3 animate-spin" /> : <Send className="h-3 w-3" />}
                    Query
                  </button>
                </div>

                {uploadStatus && (
                  <div className={`mt-3 rounded-lg border px-3 py-2 text-[10px] font-medium animate-fade-in ${
                    uploadStatus.success 
                      ? "border-emerald-500/20 bg-emerald-500/5 text-emerald-500" 
                      : "border-rose-500/20 bg-rose-500/5 text-rose-500"
                  }`}>
                    {uploadStatus.message}
                  </div>
                )}
              </div>
            </div>

            <div className="mt-6 border-t border-[var(--border-subtle)]/50 pt-5">
              <p className="label-caps font-bold mb-3">Suggested prompts</p>
              <div className="space-y-2">
                {suggestions.map((suggestion) => (
                  <button
                    key={suggestion.text}
                    onClick={() => handleSend(suggestion.text)}
                    disabled={isLoading || !activeWorkspace?.id}
                    className="w-full flex items-center justify-between gap-4 rounded-xl border border-[var(--border-subtle)] bg-[var(--bg-surface)] px-3.5 py-3 text-left shadow-sm transition-all duration-200 hover:translate-x-0.5 hover:border-[var(--border-focus)] hover:bg-[var(--bg-surface-hover)] hover:shadow-[var(--shadow-glow)] disabled:cursor-not-allowed disabled:opacity-40 cursor-pointer"
                  >
                    <span className="min-w-0 flex-1 text-[11px] font-medium text-[var(--text-primary)] truncate font-sans">
                      {suggestion.text}
                    </span>
                    <span className="inline-flex shrink-0 items-center rounded-md bg-[var(--accent-muted)] px-2 py-0.5 text-[8px] font-bold uppercase tracking-wider text-[var(--accent)] border border-[var(--accent)]/10">
                      {suggestion.category}
                    </span>
                  </button>
                ))}
              </div>
            </div>
          </section>

          {/* Column 2: System Telemetry (Metrics & Performance Health) */}
          <section className="rounded-2xl border border-[var(--border-subtle)] bg-[var(--bg-surface)] p-5 shadow-[var(--shadow-elevated)] flex flex-col justify-between backdrop-blur-md">
            <div>
              <div className="flex items-center justify-between border-b border-[var(--border-subtle)] pb-3 mb-5">
                <div>
                  <p className="label-caps font-bold">System Telemetry</p>
                  <h2 className="text-[14px] font-semibold tracking-tight text-[var(--text-primary)] mt-1">Live Engine Performance</h2>
                </div>
                <HeartPulse className="h-4 w-4 text-[var(--accent)]" />
              </div>

              <div className="grid gap-3 grid-cols-2">
                {/* Metric 1 */}
                <div className="rounded-xl border border-[var(--border-subtle)] bg-[var(--bg-root)] p-3.5 flex flex-col justify-between hover:border-[var(--border-focus)] transition-colors duration-250">
                  <span className="label-caps text-[8px] text-[var(--text-muted)] font-bold">Active Sources</span>
                  <div className="mt-2 flex items-baseline gap-1.5">
                    <span className="text-2xl font-bold tracking-tight text-[var(--text-primary)]">
                      {dashboardLoading ? "—" : connectorStats.active}
                    </span>
                    <span className="h-1.5 w-1.5 rounded-full bg-emerald-500 shadow-[0_0_4px_#10b981]" />
                  </div>
                </div>

                {/* Metric 2 */}
                <div className="rounded-xl border border-[var(--border-subtle)] bg-[var(--bg-root)] p-3.5 flex flex-col justify-between hover:border-[var(--border-focus)] transition-colors duration-250">
                  <span className="label-caps text-[8px] text-[var(--text-muted)] font-bold">Running Syncs</span>
                  <div className="mt-2 flex items-baseline gap-1.5">
                    <span className="text-2xl font-bold tracking-tight text-[var(--text-primary)]">
                      {dashboardLoading ? "—" : connectorStats.syncing}
                    </span>
                    {connectorStats.syncing > 0 && (
                      <span className="h-1.5 w-1.5 rounded-full bg-blue-500 shadow-[0_0_4px_#6366f1] animate-ping" />
                    )}
                  </div>
                </div>

                {/* Metric 3 */}
                <div className="rounded-xl border border-[var(--border-subtle)] bg-[var(--bg-root)] p-3.5 flex flex-col justify-between hover:border-[var(--border-focus)] transition-colors duration-250">
                  <span className="label-caps text-[8px] text-[var(--text-muted)] font-bold">Needs Attention</span>
                  <div className="mt-2 flex items-baseline gap-1.5">
                    <span className="text-2xl font-bold tracking-tight text-[var(--text-primary)]">
                      {dashboardLoading ? "—" : connectorStats.failed}
                    </span>
                    {connectorStats.failed > 0 && (
                      <span className="h-1.5 w-1.5 rounded-full bg-rose-500 shadow-[0_0_4px_#ef4444] animate-pulse" />
                    )}
                  </div>
                </div>

                {/* Metric 4 */}
                <div className="rounded-xl border border-[var(--border-subtle)] bg-[var(--bg-root)] p-3.5 flex flex-col justify-between hover:border-[var(--border-focus)] transition-colors duration-250">
                  <span className="label-caps text-[8px] text-[var(--text-muted)] font-bold">Last Ingestion</span>
                  <span className="mt-2 text-[10px] font-bold text-[var(--text-primary)] truncate block uppercase tracking-wider font-mono">
                    {dashboardLoading ? "Loading..." : formatRelativeTime(connectorStats.latestSync)}
                  </span>
                </div>
              </div>
            </div>

            {/* Health detail block */}
            <div className="mt-6 border-t border-[var(--border-subtle)]/50 pt-5">
              <p className="label-caps font-bold mb-3">Engine Status</p>
              <div className="rounded-xl border border-[var(--border-subtle)] bg-[var(--bg-root)] p-3.5 space-y-3 font-mono text-[9px] uppercase tracking-wider text-[var(--text-secondary)]">
                <div className="flex items-center justify-between">
                  <span>System Engine Status</span>
                  <span className="font-bold text-[var(--text-primary)]">{health?.status || "CONNECTED"}</span>
                </div>
                <div className="flex items-center justify-between border-t border-[var(--border-subtle)]/30 pt-2">
                  <span>LiteLLM Brain Gateway</span>
                  <span className="text-emerald-500 font-bold">ACTIVE</span>
                </div>
                <div className="flex items-center justify-between border-t border-[var(--border-subtle)]/30 pt-2">
                  <span>Vector Embedding Store</span>
                  <span className="text-emerald-500 font-bold">READY</span>
                </div>
              </div>
            </div>
          </section>

          {/* Column 3: Connected Sources (Data Environment) */}
          <section className="rounded-2xl border border-[var(--border-subtle)] bg-[var(--bg-surface)] p-5 shadow-[var(--shadow-elevated)] flex flex-col justify-between backdrop-blur-md">
            <div>
              <div className="flex items-center justify-between border-b border-[var(--border-subtle)] pb-3 mb-5">
                <div>
                  <p className="label-caps font-bold">Connected Sources</p>
                  <h2 className="text-[14px] font-semibold tracking-tight text-[var(--text-primary)] mt-1">Workspace Environment</h2>
                </div>
                <Cpu className="h-4 w-4 text-[var(--accent)]" />
              </div>

              {dashboardLoading ? (
                <div className="flex flex-col items-center justify-center gap-3 py-16 text-[9px] uppercase tracking-widest text-[var(--text-muted)] font-mono">
                  <Loader2 className="h-5 w-5 animate-spin text-[var(--accent)]" />
                  Refreshing connections
                </div>
              ) : connectors.length === 0 ? (
                <div className="rounded-xl border border-dashed border-[var(--border-subtle)] bg-[var(--bg-root)] px-4 py-10 text-center flex flex-col items-center justify-center">
                  <Database className="h-7 w-7 text-[var(--text-muted)] mb-3 opacity-60" />
                  <p className="text-[11px] font-bold uppercase tracking-wider text-[var(--text-primary)]">No Connectors Configured</p>
                  <p className="mt-1.5 text-[10px] text-[var(--text-secondary)] max-w-[200px] leading-relaxed">Add a connector to ground queries in Notion, Drive, or Slack.</p>
                  <button
                    onClick={() => router.push("/connectors")}
                    className="mt-5 inline-flex items-center gap-2 rounded-lg bg-[var(--accent)] px-3.5 py-1.5 text-[9px] font-bold uppercase tracking-wider text-white shadow-[var(--shadow-glow)] transition-all duration-200 hover:bg-[var(--accent-hover)] active:scale-95 cursor-pointer"
                  >
                    Setup Connector
                  </button>
                </div>
              ) : (
                <div className="space-y-2 max-h-[260px] overflow-y-auto pr-1 scrollbar-thin">
                  {connectors.map((connector) => {
                    const syncStatus = connector.latest_sync?.status || connector.status;
                    return (
                      <div
                        key={connector.id}
                        className="flex items-center justify-between gap-4 rounded-xl border border-[var(--border-subtle)] bg-[var(--bg-root)] p-3 transition-all duration-200 hover:border-[var(--border-focus)] hover:bg-[var(--bg-surface-hover)] group/item"
                      >
                        <div className="flex items-center gap-3 min-w-0">
                          <div className="h-7 w-7 rounded bg-[var(--bg-surface)] border border-[var(--border-subtle)] flex items-center justify-center text-[var(--text-primary)] shrink-0 transition-colors duration-200 group-hover/item:border-[var(--border-focus)]">
                            <ConnectorIcon type={connector.type} className="h-4 w-4" />
                          </div>
                          <div className="min-w-0">
                            <p className="truncate text-xs font-semibold text-[var(--text-primary)] capitalize">
                              {connector.type.replace(/_/g, " ")}
                            </p>
                            <p className="text-[9px] font-mono text-[var(--text-muted)] mt-0.5 uppercase tracking-wider">
                              Synced {formatRelativeTime(connector.last_synced_at)}
                            </p>
                          </div>
                        </div>
                        <span className={`shrink-0 rounded-md border px-2 py-0.5 text-[8px] font-bold uppercase tracking-wider ${statusClass(syncStatus)}`}>
                          {syncStatus}
                        </span>
                      </div>
                    );
                  })}
                </div>
              )}
            </div>


          </section>

        </div>
      </div>
    </div>
  );
}
