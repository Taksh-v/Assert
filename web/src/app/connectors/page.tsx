"use client";

import { Suspense, useCallback, useEffect, useMemo, useState } from "react";
import { useSearchParams } from "next/navigation";
import {
  AlertCircle,
  CheckCircle2,
  Clock,
  Database,
  Loader2,
  RefreshCw,
  Search,
  Settings2,
  ShieldCheck,
  Sparkles,
  Trash2,
  Zap,
} from "lucide-react";

import SourceSetupModal from "@/components/SourceSetupModal";
import ConnectorIcon from "@/components/ConnectorIcon";
import { apiFetch, ensureDefaultWorkspace, getActiveWorkspace } from "@/lib/auth";
import { useSyncRunPolling } from "@/lib/syncRuns";
import { parseUTCDate } from "@/lib/date";

interface Connector {
  id: string;
  name: string;
  type: string;
  status: "active" | "paused" | "error";
  last_synced_at?: string;
  config_summary?: Record<string, unknown>;
  document_count?: number;
  latest_sync?: SyncRun | null;
}

interface SyncRun {
  id: string;
  status: "queued" | "running" | "completed" | "completed_with_errors" | "failed" | "cancelled";
  stats?: Record<string, unknown>;
  error?: string | null;
}

interface DiscoveredItem {
  id: string;
  name: string;
  type: string;
  icon?: string | null;
  last_modified?: string;
  description?: string;
  display_type?: string;
  member_count?: number;
}

interface ConnectorMetadata {
  name: string;
  category: string;
  description: string;
  color: string;
  icon: string;
}

const CONNECTOR_METADATA: Record<string, ConnectorMetadata> = {
  notion: {
    name: "Notion",
    category: "Productivity",
    description: "Sync pages, databases, and team knowledge bases.",
    color: "#111111",
    icon: "N",
  },
  google_drive: {
    name: "Google Drive",
    category: "Cloud Storage",
    description: "Index docs, sheets, and shared files.",
    color: "#4285F4",
    icon: "G",
  },
  slack: {
    name: "Slack",
    category: "Communication",
    description: "Capture public channel knowledge and discussions.",
    color: "#4A154B",
    icon: "S",
  },
  github: {
    name: "GitHub",
    category: "Engineering",
    description: "Index docs, issues, and repository context.",
    color: "#181717",
    icon: "H",
  },
  file_upload: {
    name: "File Upload",
    category: "Files",
    description: "Upload local files (PDF, plain text, html, images, audio) directly.",
    color: "#00F5FF",
    icon: "F",
  },
};

let globalConnectorsCache: Connector[] | null = null;

function formatLastSync(isoString?: string) {
  if (!isoString) return "Never synced";

  try {
    const date = parseUTCDate(isoString);
    const now = new Date();
    const diffMs = now.getTime() - date.getTime();
    const diffMins = Math.floor(diffMs / 60000);
    if (diffMins < 1) return "Just now";
    if (diffMins < 60) return `${diffMins}m ago`;
    const diffHours = Math.floor(diffMins / 60);
    if (diffHours < 24) return `${diffHours}h ago`;
    return `${Math.floor(diffHours / 24)}d ago`;
  } catch {
    return "Unknown";
  }
}

function toneClass(status?: string) {
  if (status === "active" || status === "connected" || status === "healthy" || status === "completed") {
    return "border-emerald-500/20 bg-emerald-500/10 text-emerald-400";
  }
  if (status === "running" || status === "queued") {
    return "border-blue-500/20 bg-blue-500/10 text-blue-400 animate-pulse";
  }
  if (status === "error" || status === "failed" || status === "offline") {
    return "border-rose-500/20 bg-rose-500/10 text-rose-400";
  }
  if (status === "degraded" || status === "completed_with_errors") {
    return "border-amber-500/20 bg-amber-500/10 text-amber-400";
  }
  return "border-[var(--border-subtle)] bg-[var(--bg-root)] text-[var(--text-muted)]";
}

export default function ConnectorsPage() {
  return (
    <Suspense fallback={null}>
      <ConnectorsContent />
    </Suspense>
  );
}

function ConnectorsContent() {
  const searchParams = useSearchParams();
  const [connectors, setConnectors] = useState<Connector[]>(globalConnectorsCache || []);
  const [isLoading, setIsLoading] = useState(!globalConnectorsCache);
  const [searchQuery, setSearchQuery] = useState("");
  const [selectedCategory, setSelectedCategory] = useState("All");
  const [setupSource, setSetupSource] = useState<string | null>(null);
  const [notification, setNotification] = useState<{ type: "success" | "error"; message: string } | null>(null);
  const [selectedType, setSelectedType] = useState<string>("notion");
  const [discoveredItems, setDiscoveredItems] = useState<DiscoveredItem[]>([]);
  const [isDiscovering, setIsDiscovering] = useState(false);
  const { startPolling } = useSyncRunPolling();
  const activeWorkspace = getActiveWorkspace();

  const fetchConnectors = useCallback(async () => {
    try {
      const activeWs = getActiveWorkspace();
      if (!activeWs?.id) {
        setConnectors([]);
        return;
      }

      const response = await apiFetch(`/api/connectors?workspace_id=${activeWs.id}`);
      if (response.ok) {
        const data = (await response.json()) as Connector[];
        setConnectors(data);
        globalConnectorsCache = data;
      }
    } catch (error) {
      console.error("Failed to fetch connectors:", error);
    } finally {
      setIsLoading(false);
    }
  }, []);

  useEffect(() => {
    const connected = searchParams.get("connected");
    const connectorId = searchParams.get("connector_id");

    if (connected && connectorId) {
      queueMicrotask(() => {
        setNotification({
          type: "success",
          message: `Successfully connected to ${CONNECTOR_METADATA[connected.toLowerCase()]?.name || connected}.`,
        });
        void fetchConnectors();
      });
      window.history.replaceState({}, "", "/connectors");
    }
  }, [searchParams, fetchConnectors]);

  useEffect(() => {
    async function init() {
      await ensureDefaultWorkspace();
      void fetchConnectors();
    }

    queueMicrotask(() => void init());
  }, [fetchConnectors]);

  useEffect(() => {
    if (!notification) return undefined;
    const timer = setTimeout(() => setNotification(null), 5000);
    return () => clearTimeout(timer);
  }, [notification]);

  // Poll connectors status in the background when any of them are syncing
  useEffect(() => {
    const hasActiveSync = connectors.some((connector) => {
      const status = connector.latest_sync?.status;
      return status === "queued" || status === "running";
    });

    if (!hasActiveSync) return undefined;

    const intervalId = setInterval(() => {
      void fetchConnectors();
    }, 3000);

    return () => clearInterval(intervalId);
  }, [connectors, fetchConnectors]);

  const disconnectConnector = async (connectorId: string, connectorType: string) => {
    try {
      const response = await apiFetch(`/api/connectors/${connectorId}`, { method: "DELETE" });
      if (response.ok) {
        setNotification({
          type: "success",
          message: `${CONNECTOR_METADATA[connectorType]?.name || connectorType} disconnected.`,
        });
        await fetchConnectors();
      }
    } catch (error) {
      console.error("Failed to disconnect:", error);
      setNotification({ type: "error", message: "Failed to disconnect connector." });
    }
  };

  const resyncConnector = async (connectorId: string) => {
    try {
      const response = await apiFetch(`/api/connectors/${connectorId}/sync`, {
        method: "POST",
        body: JSON.stringify({}),
      });

      if (response.ok) {
        const data = (await response.json()) as { sync_run_id: string; message?: string };
        setNotification({ type: "success", message: data.message || "Sync started." });
        await fetchConnectors();

        startPolling(data.sync_run_id, {
          onSuccess: async (syncRun) => {
            await fetchConnectors();
            if (syncRun.status === "completed") {
              setNotification({ type: "success", message: "Sync completed successfully." });
            } else if (syncRun.status === "completed_with_errors") {
              setNotification({ type: "success", message: "Sync completed with some document errors." });
            }
          },
          onError: async (errStr) => {
            await fetchConnectors();
            setNotification({ type: "error", message: errStr });
          },
        });
      } else {
        setNotification({ type: "error", message: "Sync failed. Check backend logs." });
      }
    } catch {
      setNotification({ type: "error", message: "Failed to trigger sync." });
    }
  };

  const categoryOptions = useMemo(() => {
    const categories = new Set(Object.values(CONNECTOR_METADATA).map((meta) => meta.category));
    return ["All", ...Array.from(categories)];
  }, []);

  const filteredConnectors = useMemo(() => {
    return Object.keys(CONNECTOR_METADATA).filter((type) => {
      const meta = CONNECTOR_METADATA[type];
      const matchesSearch =
        meta.name.toLowerCase().includes(searchQuery.toLowerCase()) ||
        meta.description.toLowerCase().includes(searchQuery.toLowerCase());
      const matchesCategory = selectedCategory === "All" || meta.category === selectedCategory;
      return matchesSearch && matchesCategory;
    });
  }, [searchQuery, selectedCategory]);

  const activeSelectedType = useMemo(() => {
    if (filteredConnectors.includes(selectedType)) {
      return selectedType;
    }
    return filteredConnectors[0] || "notion";
  }, [filteredConnectors, selectedType]);

  useEffect(() => {
    let cancelled = false;

    async function loadDiscovered() {
      const instance = connectors.find((connector) => connector.type.toLowerCase() === activeSelectedType.toLowerCase());
      if (!instance || instance.status !== "active") {
        setDiscoveredItems([]);
        return;
      }

      setIsDiscovering(true);
      try {
        const response = await apiFetch(`/api/connectors/${instance.id}/discover`);
        if (response.ok && !cancelled) {
          const data = (await response.json()) as { items?: DiscoveredItem[] };
          setDiscoveredItems(data.items || []);
        } else if (!cancelled) {
          setDiscoveredItems([]);
        }
      } catch (error) {
        console.error("Failed to load discovered items:", error);
        if (!cancelled) {
          setDiscoveredItems([]);
        }
      } finally {
        if (!cancelled) {
          setIsDiscovering(false);
        }
      }
    }

    void loadDiscovered();
    return () => {
      cancelled = true;
    };
  }, [activeSelectedType, connectors]);

  const selectedMeta = CONNECTOR_METADATA[activeSelectedType];
  const selectedInstance = connectors.find((connector) => connector.type.toLowerCase() === activeSelectedType.toLowerCase());
  const selectedSyncStatus = selectedInstance?.latest_sync?.status;
  const isSelectedActive = selectedInstance?.status === "active";
  const isSelectedError = selectedInstance?.status === "error";
  const isSelectedSyncing = selectedSyncStatus === "queued" || selectedSyncStatus === "running";
  const selectedWorkspaceNameValue = selectedInstance?.config_summary?.workspace_name || selectedInstance?.config_summary?.team_name;
  const selectedWorkspaceName = typeof selectedWorkspaceNameValue === "string" ? selectedWorkspaceNameValue : "";
  const syncingCount = connectors.filter((connector) => {
    const status = connector.latest_sync?.status;
    return status === "queued" || status === "running";
  }).length;
  const failedCount = connectors.filter((connector) => connector.status === "error" || connector.latest_sync?.status === "failed").length;

  return (
    <div className="relative h-full overflow-y-auto bg-[var(--bg-root)] text-[var(--text-primary)]">
      <div className="pointer-events-none absolute right-8 top-0 h-64 w-64 rounded-full bg-[var(--accent)]/10 blur-3xl" />
      <div className="pointer-events-none absolute bottom-0 left-12 h-80 w-80 rounded-full bg-emerald-400/10 blur-3xl" />

      {notification && (
        <div
          className={`fixed right-5 top-5 z-[200] flex items-center gap-3 rounded-2xl border px-4 py-3 shadow-[var(--shadow-elevated)] ${
            notification.type === "success"
              ? "border-emerald-500/20 bg-emerald-950/85 text-emerald-400 backdrop-blur-xl"
              : "border-rose-500/20 bg-rose-950/85 text-rose-400 backdrop-blur-xl"
          }`}
        >
          {notification.type === "success" ? (
            <CheckCircle2 className="h-5 w-5 shrink-0" />
          ) : (
            <AlertCircle className="h-5 w-5 shrink-0" />
          )}
          <span className="text-sm font-medium">{notification.message}</span>
        </div>
      )}

      <div className="mx-auto flex h-full w-full max-w-[1600px] flex-col gap-6 px-6 py-6 md:px-8 md:py-8">
        <header className="rounded-[28px] border border-[var(--border-subtle)] bg-[var(--bg-surface)] p-6 shadow-[var(--shadow-elevated)] md:p-8">
          <div className="flex flex-col gap-6 lg:flex-row lg:items-start lg:justify-between">
            <div className="max-w-3xl space-y-4">
              <div className="inline-flex items-center gap-2 rounded-full border border-[var(--border-subtle)] bg-[var(--bg-root)] px-3 py-1 text-[10px] font-semibold uppercase tracking-[0.18em] text-[var(--text-secondary)]">
                <Sparkles className="h-3.5 w-3.5 text-[var(--accent)]" />
                Source workspace
              </div>
              <div className="space-y-3">
                <h1 className="text-3xl font-semibold tracking-tight text-[var(--text-primary)] md:text-4xl">
                  Connectors
                </h1>
                <p className="max-w-2xl text-sm leading-6 text-[var(--text-secondary)] md:text-[15px]">
                  A structured view of every integration, its sync posture, and the resources it contributes to grounded answers.
                </p>
              </div>
              <div className="flex flex-wrap items-center gap-2">
                <span className="rounded-full border border-[var(--border-subtle)] bg-[var(--bg-root)] px-3 py-1 text-[10px] font-semibold uppercase tracking-[0.16em] text-[var(--text-secondary)]">
                  {connectors.length} configured
                </span>
                <span className="rounded-full border border-[var(--border-subtle)] bg-[var(--bg-root)] px-3 py-1 text-[10px] font-semibold uppercase tracking-[0.16em] text-[var(--text-secondary)]">
                  {syncingCount} syncing
                </span>
                <span className="rounded-full border border-[var(--border-subtle)] bg-[var(--bg-root)] px-3 py-1 text-[10px] font-semibold uppercase tracking-[0.16em] text-[var(--text-secondary)]">
                  {failedCount} need attention
                </span>
              </div>
            </div>

            <div className="w-full max-w-2xl rounded-[24px] border border-[var(--border-subtle)] bg-[var(--bg-root)] p-4 shadow-[var(--shadow-card)]">
              <div className="flex flex-col gap-3 md:flex-row md:items-center">
                <div className="flex flex-1 items-center gap-3 rounded-2xl border border-[var(--border-subtle)] bg-[var(--bg-surface)] px-4 py-3 focus-within:border-[var(--border-focus)] transition-colors">
                  <Search className="h-4 w-4 text-[var(--text-muted)]" />
                  <input
                    type="text"
                    placeholder="Search integrations"
                    className="w-full border-none bg-transparent text-sm text-[var(--text-primary)] placeholder:text-[var(--text-muted)] focus:outline-none"
                    value={searchQuery}
                    onChange={(e) => setSearchQuery(e.target.value)}
                  />
                </div>

                <div className="flex items-center gap-3">
                  <select
                    className="rounded-2xl border border-[var(--border-subtle)] bg-[var(--bg-surface)] px-4 py-3 text-sm font-medium text-[var(--text-primary)] focus:border-[var(--border-focus)] focus:outline-none cursor-pointer"
                    value={selectedCategory}
                    onChange={(e) => setSelectedCategory(e.target.value)}
                  >
                    {categoryOptions.map((category) => (
                      <option key={category} value={category} className="bg-[var(--bg-root)]">
                        {category}
                      </option>
                    ))}
                  </select>
                </div>
              </div>
            </div>
          </div>
        </header>

        <div className="grid gap-6 lg:grid-cols-[320px_minmax(0,1fr)]">
          <aside className="rounded-[28px] border border-[var(--border-subtle)] bg-[var(--bg-surface)] p-5 shadow-[var(--shadow-card)]">
            <div className="flex items-center justify-between border-b border-[var(--border-subtle)] pb-4">
              <div>
                <p className="text-[10px] font-semibold uppercase tracking-[0.18em] text-[var(--text-muted)]">Available integrations</p>
                <p className="mt-2 text-sm text-[var(--text-secondary)]">Select a source to inspect its current status.</p>
              </div>
              <Database className="h-4 w-4 text-[var(--accent)]" />
            </div>

            <div className="mt-4 space-y-2">
              {isLoading ? (
                <div className="space-y-3 py-4">
                  {[1, 2, 3, 4].map((index) => (
                    <div key={index} className="h-20 rounded-2xl border border-[var(--border-subtle)] bg-[var(--bg-root)] animate-pulse" />
                  ))}
                </div>
              ) : filteredConnectors.length === 0 ? (
                <div className="rounded-2xl border border-dashed border-[var(--border-subtle)] bg-[var(--bg-root)] px-4 py-8 text-center">
                  <p className="text-sm font-medium text-[var(--text-primary)]">No integrations found.</p>
                  <p className="mt-2 text-sm text-[var(--text-secondary)]">Try a different search or category.</p>
                </div>
              ) : (
                filteredConnectors.map((type) => {
                  const meta = CONNECTOR_METADATA[type];
                  const instance = connectors.find((connector) => connector.type.toLowerCase() === type.toLowerCase());
                  const syncStatus = instance?.latest_sync?.status;
                  const isSyncing = syncStatus === "queued" || syncStatus === "running";
                  const isActive = instance?.status === "active";
                  const isError = instance?.status === "error";
                  const isSelected = activeSelectedType === type;

                  return (
                    <button
                      key={type}
                      onClick={() => setSelectedType(type)}
                      className={`relative flex w-full items-center justify-between gap-3 rounded-2xl border p-4 text-left transition hover:-translate-y-0.5 hover:bg-[var(--bg-surface-hover)] ${
                        isSelected
                          ? "border-[var(--border-focus)] bg-[var(--accent-muted)] shadow-[var(--shadow-glow)]"
                          : "border-[var(--border-subtle)] bg-[var(--bg-surface)]"
                      }`}
                    >
                      <div className="flex min-w-0 items-center gap-3">
                        <div className="flex h-10 w-10 shrink-0 items-center justify-center rounded-xl border border-[var(--border-subtle)] bg-[var(--bg-root)] text-[var(--text-primary)] shadow-sm">
                          <ConnectorIcon type={type} className="h-5 w-5" />
                        </div>
                        <div className="min-w-0">
                          <p className="truncate text-sm font-semibold text-[var(--text-primary)]">{meta.name}</p>
                          <p className="mt-1 truncate text-xs text-[var(--text-secondary)]">{meta.category}</p>
                          <p className="mt-1 line-clamp-2 text-xs text-[var(--text-muted)]">{meta.description}</p>
                        </div>
                      </div>

                      <div className="flex shrink-0 flex-col items-end gap-2">
                        <span className={`inline-flex items-center rounded-full border px-2.5 py-1 text-[10px] font-semibold uppercase tracking-[0.16em] ${toneClass(syncStatus || instance?.status)}`}>
                          {syncStatus || instance?.status || "inactive"}
                        </span>
                        <span
                          className={`h-2.5 w-2.5 rounded-full ${
                            isSyncing ? "bg-blue-500" : isActive ? "bg-emerald-500" : isError ? "bg-rose-500" : "bg-slate-300"
                          }`}
                        />
                      </div>
                    </button>
                  );
                })
              )}
            </div>
          </aside>

          <section className="space-y-6">
            {!activeWorkspace?.id ? (
              <div className="rounded-[28px] border border-rose-200 bg-rose-50 p-5 text-sm text-rose-700 shadow-[var(--shadow-card)]">
                No active workspace was found. Select a workspace before configuring connectors.
              </div>
            ) : (
              <>
                <div className="rounded-[28px] border border-[var(--border-subtle)] bg-[var(--bg-surface)] p-6 shadow-[var(--shadow-elevated)]">
                  <div className="flex flex-col gap-5 lg:flex-row lg:items-start lg:justify-between">
                    <div className="flex min-w-0 items-start gap-4">
                      <div className="flex h-12 w-12 shrink-0 items-center justify-center rounded-xl border border-[var(--border-subtle)] bg-[var(--bg-root)] text-[var(--text-primary)] shadow-sm">
                        <ConnectorIcon type={activeSelectedType} className="h-6 w-6" />
                      </div>
                      <div className="min-w-0 space-y-2">
                        <div className="flex flex-wrap items-center gap-2">
                          <h2 className="text-2xl font-semibold tracking-tight text-[var(--text-primary)]">{selectedMeta.name}</h2>
                          <span className="rounded-full border border-[var(--border-subtle)] bg-[var(--bg-root)] px-3 py-1 text-[10px] font-semibold uppercase tracking-[0.16em] text-[var(--text-secondary)]">
                            {selectedMeta.category}
                          </span>
                          <span className={`rounded-full border px-3 py-1 text-[10px] font-semibold uppercase tracking-[0.16em] ${toneClass(selectedSyncStatus || selectedInstance?.status)}`}>
                            {selectedSyncStatus || selectedInstance?.status || "inactive"}
                          </span>
                        </div>
                        <p className="max-w-3xl text-sm leading-6 text-[var(--text-secondary)]">
                          {selectedMeta.description}
                        </p>
                        {selectedWorkspaceName ? (
                          <p className="text-sm text-[var(--text-muted)]">
                            Workspace scope: <span className="font-medium text-[var(--text-primary)]">{selectedWorkspaceName}</span>
                          </p>
                        ) : null}
                      </div>
                    </div>

                    <div className="flex flex-wrap items-center gap-2">
                      {isSelectedActive && selectedInstance ? (
                        <>
                          <button
                            onClick={() => resyncConnector(selectedInstance.id)}
                            disabled={isSelectedSyncing}
                            className="inline-flex items-center gap-2 rounded-full border border-[var(--border-subtle)] bg-[var(--bg-surface)] px-4 py-2 text-sm font-medium text-[var(--text-primary)] transition hover:border-[var(--border-focus)] hover:bg-[var(--bg-surface-hover)] disabled:cursor-not-allowed disabled:opacity-50"
                          >
                            <RefreshCw className={`h-4 w-4 ${isSelectedSyncing ? "animate-spin text-[var(--accent)]" : "text-[var(--text-muted)]"}`} />
                            Sync now
                          </button>
                          <button
                            onClick={() => disconnectConnector(selectedInstance.id, selectedType)}
                            className="inline-flex items-center gap-2 rounded-full border border-rose-500/20 bg-rose-950/20 px-4 py-2 text-sm font-medium text-rose-400 transition hover:bg-rose-950/40 hover:border-rose-500/30 cursor-pointer"
                          >
                            <Trash2 className="h-4 w-4" />
                            Disconnect
                          </button>
                        </>
                      ) : null}

                      <button
                        onClick={() => setSetupSource(selectedType)}
                        className="inline-flex items-center gap-2 rounded-full bg-[var(--accent)] px-4 py-2 text-sm font-semibold text-white transition hover:bg-[var(--accent-hover)]"
                      >
                        {isSelectedActive ? <Settings2 className="h-4 w-4" /> : <Zap className="h-4 w-4" />}
                        {isSelectedActive ? "Manage source" : "Connect source"}
                      </button>
                    </div>
                  </div>
                </div>

                <div className="grid gap-4 md:grid-cols-2 xl:grid-cols-4">
                  <div className="rounded-[24px] border border-[var(--border-subtle)] bg-[var(--bg-surface)] p-5 shadow-[var(--shadow-card)]">
                    <div className="flex items-start justify-between gap-3">
                      <div>
                        <p className="text-[10px] font-semibold uppercase tracking-[0.18em] text-[var(--text-muted)]">Connection state</p>
                        <p className="mt-3 text-lg font-semibold text-[var(--text-primary)]">
                          {isSelectedSyncing ? "Sync running" : isSelectedActive ? "Active" : isSelectedError ? "Error" : "Not configured"}
                        </p>
                      </div>
                      <ShieldCheck className="h-5 w-5 text-[var(--accent)]" />
                    </div>
                  </div>

                  <div className="rounded-[24px] border border-[var(--border-subtle)] bg-[var(--bg-surface)] p-5 shadow-[var(--shadow-card)]">
                    <div className="flex items-start justify-between gap-3">
                      <div>
                        <p className="text-[10px] font-semibold uppercase tracking-[0.18em] text-[var(--text-muted)]">Indexed documents</p>
                        <p className="mt-3 text-3xl font-semibold tracking-tight text-[var(--text-primary)]">
                          {isSelectedActive ? (selectedInstance?.document_count ?? 0) : "—"}
                        </p>
                      </div>
                      <Database className="h-5 w-5 text-[var(--accent)]" />
                    </div>
                  </div>

                  <div className="rounded-[24px] border border-[var(--border-subtle)] bg-[var(--bg-surface)] p-5 shadow-[var(--shadow-card)]">
                    <div className="flex items-start justify-between gap-3">
                      <div className="min-w-0">
                        <p className="text-[10px] font-semibold uppercase tracking-[0.18em] text-[var(--text-muted)]">Last sync</p>
                        <p className="mt-3 truncate text-lg font-semibold text-[var(--text-primary)]">
                          {isSelectedSyncing ? "Running..." : formatLastSync(selectedInstance?.last_synced_at)}
                        </p>
                      </div>
                      <Clock className="h-5 w-5 text-[var(--accent)]" />
                    </div>
                  </div>

                  <div className="rounded-[24px] border border-[var(--border-subtle)] bg-[var(--bg-surface)] p-5 shadow-[var(--shadow-card)]">
                    <div className="flex items-start justify-between gap-3">
                      <div>
                        <p className="text-[10px] font-semibold uppercase tracking-[0.18em] text-[var(--text-muted)]">Workspace sources</p>
                        <p className="mt-3 text-3xl font-semibold tracking-tight text-[var(--text-primary)]">{connectors.length}</p>
                      </div>
                      <Sparkles className="h-5 w-5 text-[var(--accent)]" />
                    </div>
                  </div>
                </div>

                <div className="grid gap-6 xl:grid-cols-[minmax(0,1.1fr)_minmax(320px,0.9fr)]">
                  <div className="rounded-[28px] border border-[var(--border-subtle)] bg-[var(--bg-surface)] p-6 shadow-[var(--shadow-card)]">
                    <div className="flex items-center justify-between border-b border-[var(--border-subtle)] pb-4">
                      <div>
                        <p className="text-[10px] font-semibold uppercase tracking-[0.18em] text-[var(--text-muted)]">Grounded resources</p>
                        <h3 className="mt-2 text-lg font-semibold tracking-tight text-[var(--text-primary)]">What this connector is feeding into the workspace.</h3>
                      </div>
                      <Database className="h-5 w-5 text-[var(--accent)]" />
                    </div>

                    <div className="mt-4">
                      {isDiscovering ? (
                        <div className="flex items-center justify-center gap-2 rounded-2xl border border-dashed border-[var(--border-subtle)] bg-[var(--bg-root)] py-10 text-sm text-[var(--text-secondary)]">
                          <Loader2 className="h-4 w-4 animate-spin text-[var(--accent)]" />
                          Scanning indexed resources
                        </div>
                      ) : !isSelectedActive ? (
                        <div className="rounded-2xl border border-dashed border-[var(--border-subtle)] bg-[var(--bg-root)] px-5 py-10 text-center">
                          <p className="text-sm font-medium text-[var(--text-primary)]">Connect this source to preview indexed content.</p>
                          <p className="mt-2 text-sm text-[var(--text-secondary)]">
                            Discovery results and resource previews appear here once the connector is active.
                          </p>
                        </div>
                      ) : discoveredItems.length === 0 ? (
                        <div className="rounded-2xl border border-dashed border-[var(--border-subtle)] bg-[var(--bg-root)] px-5 py-10 text-center">
                          <p className="text-sm font-medium text-[var(--text-primary)]">No indexed files or channels found.</p>
                          <p className="mt-2 text-sm text-[var(--text-secondary)]">
                            The connector is active, but discovery hasn&apos;t surfaced any content yet.
                          </p>
                        </div>
                      ) : (
                        <div className="space-y-3">
                          {discoveredItems.slice(0, 8).map((item) => (
                            <div
                              key={item.id}
                              className="flex items-center justify-between gap-4 rounded-2xl border border-[var(--border-subtle)] bg-[var(--bg-root)] px-4 py-3 transition hover:border-[var(--border-focus)] hover:bg-[var(--bg-surface-hover)]"
                            >
                              <div className="min-w-0">
                                <div className="flex items-center gap-2">
                                  {item.icon ? <span className="text-sm">{item.icon}</span> : null}
                                  <p className="truncate text-sm font-medium text-[var(--text-primary)]">{item.name}</p>
                                </div>
                                <p className="mt-1 text-xs text-[var(--text-secondary)]">
                                  {item.display_type || item.type}
                                  {item.last_modified ? ` · ${formatLastSync(item.last_modified)}` : ""}
                                </p>
                                {item.description ? <p className="mt-1 line-clamp-2 text-xs text-[var(--text-muted)]">{item.description}</p> : null}
                              </div>
                              <span className="shrink-0 rounded-full border border-[var(--border-subtle)] bg-[var(--bg-root)] px-2.5 py-1 text-[10px] font-semibold uppercase tracking-[0.16em] text-[var(--text-secondary)]">
                                {item.member_count !== undefined ? `${item.member_count} members` : "Indexed"}
                              </span>
                            </div>
                          ))}
                        </div>
                      )}
                    </div>
                  </div>

                  <div className="space-y-6">
                    <div className="rounded-[28px] border border-[var(--border-subtle)] bg-[var(--bg-surface)] p-6 shadow-[var(--shadow-card)]">
                      <div className="flex items-center gap-2 border-b border-[var(--border-subtle)] pb-4">
                        <Clock className="h-4 w-4 text-[var(--text-muted)]" />
                        <div>
                          <p className="text-[10px] font-semibold uppercase tracking-[0.18em] text-[var(--text-muted)]">Synchronization log</p>
                          <h3 className="mt-1 text-base font-semibold tracking-tight text-[var(--text-primary)]">Pipeline history</h3>
                        </div>
                      </div>

                      <div className="mt-4 space-y-4 text-sm">
                        <div className="flex items-center justify-between gap-3">
                          <span className="text-[var(--text-secondary)] font-mono text-[11px] uppercase tracking-wider">Latest ingestion sync</span>
                          <span className="font-mono text-[11px] font-medium text-[var(--text-primary)]">
                            {isSelectedSyncing ? "Running..." : formatLastSync(selectedInstance?.last_synced_at)}
                          </span>
                        </div>

                        <div className="flex items-center justify-between gap-3">
                          <span className="text-[var(--text-secondary)] font-mono text-[11px] uppercase tracking-wider">Current status</span>
                          <span className={`rounded-full border px-2.5 py-0.5 text-[9px] font-mono font-semibold uppercase tracking-[0.16em] ${toneClass(selectedSyncStatus || selectedInstance?.status)}`}>
                            {selectedSyncStatus || selectedInstance?.status || "inactive"}
                          </span>
                        </div>

                        {selectedInstance?.latest_sync?.error && (
                          <div className="rounded-2xl border border-rose-500/20 bg-rose-950/20 p-4 text-sm leading-6 text-rose-400 font-mono">
                            {typeof selectedInstance.latest_sync.error === 'string' 
                              ? selectedInstance.latest_sync.error 
                              : JSON.stringify(selectedInstance.latest_sync.error)}
                          </div>
                        )}
                      </div>
                    </div>
                  </div>
                </div>
              </>
            )}
          </section>
        </div>
      </div>

      {setupSource && (
        <SourceSetupModal
          type={setupSource}
          metadata={CONNECTOR_METADATA[setupSource]}
          workspaceId={activeWorkspace?.id || ""}
          onClose={() => setSetupSource(null)}
          onConnect={() => {
            void fetchConnectors();
            setNotification({ type: "success", message: "Sync started in background." });
          }}
        />
      )}
    </div>
  );
}
