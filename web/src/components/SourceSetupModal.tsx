"use client";

import { useState, useEffect, useCallback } from "react";
import { X, Shield, Lock, Loader2, CheckCircle2, ChevronRight, Settings, AlertCircle, RefreshCw, Zap } from "lucide-react";
import { apiFetch } from "@/lib/auth";
import { useSyncRunPolling } from "@/lib/syncRuns";

interface SourceMetadata {
  name: string;
  color: string;
  icon: string;
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

interface SyncRun {
  id: string;
  status: "queued" | "running" | "completed" | "completed_with_errors" | "failed" | "cancelled";
  stats?: Record<string, unknown>;
  error?: string | null;
}

interface SourceSetupModalProps {
  type: string;
  metadata: SourceMetadata;
  onClose: () => void;
  onConnect: (config: Record<string, string>) => void;
  workspaceId: string;
}

export default function SourceSetupModal({ type, metadata, onClose, onConnect, workspaceId }: SourceSetupModalProps) {
  const [step, setStep] = useState<"setup" | "discover" | "syncing" | "done" | "error">("setup");
  const [showAdvanced, setShowAdvanced] = useState(false);
  const [config, setConfig] = useState<Record<string, string>>({});
  const [isLoading, setIsLoading] = useState(false);
  const [isDiscovering, setIsDiscovering] = useState(false);
  const [discoveredItems, setDiscoveredItems] = useState<DiscoveredItem[]>([]);
  const [selectedIds, setSelectedIds] = useState<string[]>([]);
  const [connectorId, setConnectorId] = useState<string | null>(null);
  const [errorMessage, setErrorMessage] = useState<string>("");
  const [syncProgress, setSyncProgress] = useState<string>("");
  const [doneMessage, setDoneMessage] = useState<string>("Your brain is now live. Ask questions and get grounded answers from your connected sources.");
  const [, setOauthConfigured] = useState<boolean>(true);
  const [hasDirectToken, setHasDirectToken] = useState<boolean>(false);
  const [isInitialLoading, setIsInitialLoading] = useState(true);
  const { startPolling } = useSyncRunPolling();
  const sourceIconSrc =
    type === "notion"
      ? "https://www.notion.so/favicon.ico"
      : type === "google_drive"
        ? "https://www.google.com/favicon.ico"
        : null;

  const discoverResources = useCallback(async (cId: string) => {
    setIsDiscovering(true);
    try {
      const discoveryRes = await apiFetch(`/api/connectors/${cId}/discover`);
      if (discoveryRes.ok) {
        const data = await discoveryRes.json() as { items?: DiscoveredItem[] };
        setDiscoveredItems(data.items || []);
      } else {
        const errorData = await discoveryRes.json();
        setErrorMessage(errorData.detail || "Discovery failed");
        setStep("error");
      }
    } catch (error) {
      console.error("Discovery fetch failed:", error);
      setErrorMessage("Failed to connect to backend. Is the server running?");
      setStep("error");
    } finally {
      setIsDiscovering(false);
    }
  }, []);

  const handleOAuth = async () => {
    setIsLoading(true);
    setErrorMessage("");
    try {
      // Step 1: Get the Authorization URL from the backend (uses real .env credentials)
      const response = await apiFetch(`/api/oauth/authorize/${type}?workspace_id=${workspaceId}`);

      if (!response.ok) {
        const errorData = await response.json();
        setErrorMessage(errorData.detail || "OAuth not configured for this source");
        setOauthConfigured(false);
        setIsLoading(false);
        return;
      }

      const data = await response.json();

      // Handle Slack direct token (no OAuth popup needed)
      if (data.direct_token) {
        setHasDirectToken(true);
        await handleSlackDirectConnect();
        return;
      }

      if (!data.url) {
        setErrorMessage("No authorization URL returned");
        setIsLoading(false);
        return;
      }

      // Step 2: Open OAuth popup
      const width = 600, height = 700;
      const left = Math.round((window.innerWidth - width) / 2);
      const top = Math.round((window.innerHeight - height) / 2);
      const popup = window.open(data.url, "oauth-popup", `width=${width},height=${height},left=${left},top=${top}`);

      // Step 3: Poll for popup closure (fallback if postMessage doesn't work)
      if (popup) {
        const pollTimer = setInterval(async () => {
          if (popup.closed) {
            clearInterval(pollTimer);
            // If we haven't received a postMessage, check if connector was created
            if (!connectorId && step === "setup") {
              await checkForExistingConnector();
            }
          }
        }, 1000);

        // Cleanup after 2 minutes
        setTimeout(() => {
          clearInterval(pollTimer);
          if (step === "setup") {
            setIsLoading(false);
          }
        }, 120000);
      }
    } catch (error) {
      console.error("OAuth flow failed", error);
      setErrorMessage("Failed to start OAuth flow. Check backend connection.");
      setIsLoading(false);
    }
  };

  const handleSlackDirectConnect = async () => {
    try {
      const response = await apiFetch(`/api/auth/slack/direct?workspace_id=${workspaceId}`, { method: "POST" });
      if (response.ok) {
        const data = await response.json();
        setConnectorId(data.connector_id);
        setStep("discover");
        setIsDiscovering(true);
        await discoverResources(data.connector_id);
      } else {
        const errorData = await response.json();
        setErrorMessage(errorData.detail || "Slack direct connection failed");
        setStep("error");
      }
    } catch {
      setErrorMessage("Failed to connect Slack");
      setStep("error");
    } finally {
      setIsLoading(false);
    }
  };

  const checkForExistingConnector = useCallback(async () => {
    // After popup closes or on mount, check if the backend has an active connector
    try {
      const response = await apiFetch(`/api/connectors?workspace_id=${workspaceId}`);
      if (response.ok) {
        const connectors = await response.json() as Array<{ id: string; type: string; status: string; config_summary?: Record<string, unknown> }>;
        const match = connectors.find(
          (c) => c.type === type &&
            c.status === "active" &&
            (c.config_summary?.oauth || c.config_summary?.direct_token)
        );
        if (match) {
          setConnectorId(match.id);
          setStep("discover");
          setIsDiscovering(true);
          await discoverResources(match.id);
          return true;
        }
      }
    } catch (e) {
      console.error("Failed to check for existing connector", e);
    }
    return false;
  }, [discoverResources, type, workspaceId]);

  // Check for existing connector on mount
  useEffect(() => {
    const init = async () => {
      setIsInitialLoading(true);
      await checkForExistingConnector();
      setIsInitialLoading(false);
    };
    void init();
  }, [checkForExistingConnector]);

  // Listen for OAuth popup messages
  useEffect(() => {
    const handler = (event: MessageEvent) => {
      if (event.data?.type === "oauth-callback") {
        if (event.data.status === "success") {
          const cId = event.data.connector_id;
          setConnectorId(cId);
          setStep("discover");
          setIsDiscovering(true);
          void discoverResources(cId);
        } else if (event.data.status === "error") {
          setErrorMessage(event.data.error || "OAuth flow failed");
          setStep("error");
        }
        setIsLoading(false);
      }
    };

    window.addEventListener("message", handler);
    return () => window.removeEventListener("message", handler);
  }, [discoverResources]);

  const handleManualToken = async () => {
    setIsLoading(true);
    setErrorMessage("");
    try {
      const token = config.api_key;
      if (!token) {
        setErrorMessage("Please enter a token");
        setIsLoading(false);
        return;
      }

      // Create connector with manual token
      const response = await apiFetch(`/api/connectors`, {
        method: "POST",
        body: JSON.stringify({
          workspace_id: workspaceId,
          type: type,
          config: { access_token: token },
        }),
      });

      if (!response.ok) {
        const errorData = await response.json();
        setErrorMessage(errorData.detail || "Failed to create connector");
        setIsLoading(false);
        return;
      }

      const connector = (await response.json()) as { id: string };
      setConnectorId(connector.id);
      setStep("discover");
      setIsDiscovering(true);
      await discoverResources(connector.id);
    } catch {
      setErrorMessage("Connection failed. Check your token and try again.");
    } finally {
      setIsLoading(false);
    }
  };

  const handleSync = async () => {
    if (!connectorId) return;

    setStep("syncing");
    setSyncProgress("Starting sync...");

    try {
      const response = await apiFetch(`/api/connectors/${connectorId}/sync`, {
        method: "POST",
        body: JSON.stringify({ selected_ids: selectedIds.length > 0 ? selectedIds : null }),
      });

      if (response.ok) {
        const started = await response.json() as { sync_run_id: string; status: string; message?: string };
        setSyncProgress(started.message || "Sync queued...");
        startPolling(started.sync_run_id, {
          onSuccess: (syncRun) => {
            if (syncRun.status === "completed") {
              setDoneMessage("Knowledge captured successfully. Your connected source is ready for grounded answers.");
              setStep("done");
              setTimeout(() => {
                onConnect(config);
                onClose();
              }, 2000);
            } else if (syncRun.status === "completed_with_errors") {
              const failed = typeof syncRun.stats?.failed === "number" ? syncRun.stats.failed : "some";
              setDoneMessage(`Sync completed with ${failed} document errors. Successful documents are available now.`);
              setStep("done");
              setTimeout(() => {
                onConnect(config);
                onClose();
              }, 2600);
            }
          },
          onError: (errStr) => {
            setErrorMessage(errStr);
            setStep("error");
          },
          onProgress: (progText) => {
            setSyncProgress(progText);
          }
        });
      } else {
        const errorData = await response.json();
        setErrorMessage(errorData.detail || "Sync failed");
        setStep("error");
      }
    } catch {
      setErrorMessage("Sync failed. Check backend logs for details.");
      setStep("error");
    }
  };

  const toggleSelectAll = () => {
    if (selectedIds.length === discoveredItems.length) {
      setSelectedIds([]);
    } else {
      setSelectedIds(discoveredItems.map((item) => item.id));
    }
  };

  const formatTimeAgo = (isoString?: string) => {
    if (!isoString) return "";
    try {
      const date = new Date(isoString);
      const now = new Date();
      const diffMs = now.getTime() - date.getTime();
      const diffMins = Math.floor(diffMs / 60000);
      if (diffMins < 60) return `${diffMins}m ago`;
      const diffHours = Math.floor(diffMins / 60);
      if (diffHours < 24) return `${diffHours}h ago`;
      const diffDays = Math.floor(diffHours / 24);
      return `${diffDays}d ago`;
    } catch {
      return "";
    }
  };

  return (
    <div className="fixed inset-0 z-[100] flex items-center justify-center bg-black/60 backdrop-blur-xl p-6">
      <div className="glass-card w-full max-w-xl overflow-hidden relative border-white/10 shadow-[0_0_80px_rgba(0,0,0,0.8)] bg-slate-900 rounded-[2.5rem] transform transition-all duration-500 scale-100">
        {/* Header */}
        <div className="p-10 border-b border-white/5 flex items-center justify-between bg-gradient-to-br from-white/[0.03] to-transparent">
          <div className="flex items-center gap-6">
            <div
              className="h-16 w-16 rounded-[1.25rem] flex items-center justify-center text-3xl font-black text-white shadow-2xl"
              style={{ backgroundColor: metadata.color, boxShadow: `0 20px 40px ${metadata.color}44` }}
            >
              {metadata.icon}
            </div>
            <div>
              <h2 className="text-2xl font-black text-white tracking-tight">Connect {metadata.name}</h2>
              <p className="text-xs text-zinc-500 font-bold uppercase tracking-widest mt-1 opacity-60">
                {step === "setup" && "Secure Authorization"}
                {step === "discover" && "Browsing Your Knowledge"}
                {step === "syncing" && "Indexing Your Brain"}
                {step === "done" && "All Set!"}
                {step === "error" && "Something Went Wrong"}
              </p>
            </div>
          </div>
          <button
            onClick={onClose}
            className="h-12 w-12 rounded-full hover:bg-white/5 flex items-center justify-center transition-all group"
          >
            <X className="h-6 w-6 text-zinc-500 group-hover:text-white transition-colors" />
          </button>
        </div>

        {/* Content */}
        <div className="p-10 space-y-8">
          {isInitialLoading ? (
            <div className="flex flex-col items-center justify-center py-20 gap-4">
              <Loader2 className="animate-spin text-blue-500 h-10 w-10" />
              <p className="text-xs font-black text-zinc-500 uppercase tracking-widest">Validating Connection...</p>
            </div>
          ) : step === "setup" && (
            <div className="space-y-8">
              <div className="flex flex-col items-center text-center space-y-4 py-4">
                <div className="p-4 bg-blue-500/10 rounded-full">
                  <Lock className="w-8 h-8 text-blue-400" />
                </div>
                <h3 className="text-xl font-bold text-white">
                  {hasDirectToken ? "Direct Connection" : "One-Click Authorization"}
                </h3>
                <p className="text-sm text-zinc-500 max-w-[320px] leading-relaxed">
                  {type === "slack" && hasDirectToken
                    ? "Your Slack bot token is configured. Connect instantly to start indexing channels."
                    : "We'll open a secure window for you to authorize Assest. No tokens or manual setup required."
                  }
                </p>
              </div>

              {errorMessage && (
                <div className="flex items-center gap-3 p-4 rounded-xl bg-red-500/10 border border-red-500/20">
                  <AlertCircle className="w-5 h-5 text-red-400 shrink-0" />
                  <p className="text-sm text-red-400">{errorMessage}</p>
                </div>
              )}

              <button
                onClick={handleOAuth}
                disabled={isLoading}
                className="w-full h-16 rounded-2xl bg-white text-black font-black text-lg flex items-center justify-center gap-4 transition-all hover:scale-[1.02] active:scale-[0.98] shadow-2xl shadow-white/10 disabled:opacity-50 disabled:hover:scale-100"
              >
                {isLoading ? (
                  <Loader2 className="h-6 w-6 animate-spin" />
                ) : (
                  <>
                    {type === "slack" ? (
                      <Zap className="w-6 h-6" />
                    ) : sourceIconSrc ? (
                      // eslint-disable-next-line @next/next/no-img-element
                      <img
                        src={sourceIconSrc}
                        className="w-6 h-6"
                        alt=""
                        onError={(e) => { (e.target as HTMLImageElement).style.display = 'none'; }}
                      />
                    ) : null}
                    {type === "slack" && hasDirectToken ? "Connect Slack" : `Authorize ${metadata.name}`}
                    <ChevronRight className="w-5 h-5" />
                  </>
                )}
              </button>

              <div className="pt-4 flex flex-col items-center gap-4">
                <button
                  onClick={() => setShowAdvanced(!showAdvanced)}
                  className="text-[10px] font-black text-zinc-500 uppercase tracking-widest hover:text-white transition-colors flex items-center gap-2"
                >
                  <Settings className="w-3 h-3" />
                  {showAdvanced ? "Hide Advanced Setup" : "Manual Token Setup (Advanced)"}
                </button>

                {showAdvanced && (
                  <div className="w-full space-y-4 animate-in slide-in-from-top-4 duration-300">
                    <input
                      type="password"
                      placeholder={type === "notion" ? "Enter Notion integration token..." : type === "google_drive" ? "Paste OAuth access token..." : "Enter Slack bot token..."}
                      className="w-full h-14 px-6 rounded-2xl bg-white/5 border border-white/10 text-sm text-white focus:outline-none focus:border-blue-500/50 placeholder:text-zinc-600"
                      onChange={(e) => setConfig({ ...config, api_key: e.target.value })}
                    />
                    <button
                      onClick={handleManualToken}
                      disabled={isLoading || !config.api_key}
                      className="w-full h-14 rounded-2xl bg-zinc-800 text-white font-bold text-sm hover:bg-zinc-700 transition-colors disabled:opacity-50"
                    >
                      {isLoading ? <Loader2 className="h-5 w-5 animate-spin mx-auto" /> : "Verify Manual Connection"}
                    </button>
                  </div>
                )}
              </div>
            </div>
          )}

          {step === "discover" && (
            <div className="space-y-6">
              <div className="flex items-center justify-between">
                <h3 className="text-lg font-bold text-white">Pick Your Knowledge</h3>
                <div className="flex items-center gap-3">
                  <button
                    onClick={toggleSelectAll}
                    className="text-[10px] font-black text-blue-400 uppercase tracking-widest hover:text-blue-300 transition-colors"
                  >
                    {selectedIds.length === discoveredItems.length ? "Deselect All" : "Select All"}
                  </button>
                  <span className="text-[10px] font-black text-blue-400 uppercase bg-blue-400/10 px-3 py-1 rounded-full">
                    {selectedIds.length} / {discoveredItems.length}
                  </span>
                </div>
              </div>
              <div className="max-h-[320px] overflow-y-auto space-y-3 pr-2 custom-scrollbar">
                {isDiscovering ? (
                  <div className="flex flex-col items-center justify-center py-20 gap-4">
                    <Loader2 className="animate-spin text-blue-500 h-10 w-10" />
                    <p className="text-xs font-black text-zinc-500 uppercase tracking-widest">Scanning Workspace...</p>
                  </div>
                ) : discoveredItems.length === 0 ? (
                  <div className="flex flex-col items-center justify-center py-20 gap-4">
                    <AlertCircle className="text-zinc-600 h-10 w-10" />
                    <p className="text-xs font-black text-zinc-500 uppercase tracking-widest">No Resources Found</p>
                    <p className="text-xs text-zinc-600 text-center max-w-[250px]">
                      Make sure you have shared pages/files with the Assest integration.
                    </p>
                  </div>
                ) : (
                  discoveredItems.map((item) => (
                    <div
                      key={item.id}
                      onClick={() => {
                        if (selectedIds.includes(item.id)) setSelectedIds(selectedIds.filter(id => id !== item.id));
                        else setSelectedIds([...selectedIds, item.id]);
                      }}
                      className={`flex items-center gap-4 p-5 rounded-[1.5rem] border transition-all cursor-pointer group ${selectedIds.includes(item.id)
                          ? "bg-blue-600/10 border-blue-500/50 shadow-lg shadow-blue-500/5"
                          : "bg-white/[0.03] border-white/5 hover:bg-white/[0.08]"
                        }`}
                    >
                      <div className={`w-6 h-6 rounded-lg border flex items-center justify-center transition-all ${selectedIds.includes(item.id) ? "bg-blue-500 border-blue-500" : "border-white/20 bg-transparent"
                        }`}>
                        {selectedIds.includes(item.id) && <CheckCircle2 className="w-4 h-4 text-white" />}
                      </div>
                      <div className="flex-1 min-w-0">
                        <div className="flex items-center gap-2">
                          {item.icon && <span className="text-sm">{item.icon}</span>}
                          <p className={`text-sm font-bold transition-colors truncate ${selectedIds.includes(item.id) ? "text-blue-400" : "text-white"}`}>
                            {item.name}
                          </p>
                        </div>
                        <div className="flex items-center gap-2 mt-1">
                          <span className="text-[9px] text-zinc-500 uppercase font-black tracking-widest bg-white/5 px-2 py-0.5 rounded-md">
                            {item.display_type || item.type}
                          </span>
                          {item.last_modified && (
                            <span className="text-[9px] text-zinc-600 font-bold">
                              {formatTimeAgo(item.last_modified)}
                            </span>
                          )}
                          {item.member_count !== undefined && item.member_count > 0 && (
                            <span className="text-[9px] text-zinc-600 font-bold">
                              {item.member_count} members
                            </span>
                          )}
                        </div>
                        {item.description && (
                          <p className="text-[10px] text-zinc-600 mt-1 truncate">{item.description}</p>
                        )}
                      </div>
                    </div>
                  ))
                )}
              </div>

              {!isDiscovering && discoveredItems.length > 0 && (
                <button
                  onClick={handleSync}
                  className="w-full h-16 rounded-2xl bg-white text-black font-black text-lg flex items-center justify-center gap-3 shadow-xl shadow-white/10 mt-4 hover:scale-[1.02] active:scale-[0.98] transition-all"
                >
                  {selectedIds.length > 0
                    ? `Sync ${selectedIds.length} Selected`
                    : "Sync All Knowledge"
                  }
                  <CheckCircle2 className="w-5 h-5" />
                </button>
              )}
            </div>
          )}

          {step === "syncing" && (
            <div className="py-16 text-center text-white space-y-8">
              <div className="relative w-24 h-24 mx-auto">
                <div className="absolute inset-0 bg-blue-500/30 blur-3xl rounded-full animate-pulse"></div>
                <div className="relative p-7 bg-slate-800 rounded-[2rem] border border-blue-500/50 flex items-center justify-center shadow-2xl">
                  <div className="absolute inset-0 border-2 border-blue-400 border-t-transparent rounded-[2rem] animate-spin"></div>
                  <RefreshCw className="h-12 w-12 text-blue-400 animate-spin" style={{ animationDuration: '3s' }} />
                </div>
              </div>
              <div className="space-y-3">
                <h3 className="text-2xl font-black">Ingesting Knowledge</h3>
                <p className="text-sm text-zinc-500 max-w-[300px] mx-auto leading-relaxed">
                  {syncProgress || "Processing documents through the ingestion pipeline..."}
                </p>
              </div>
            </div>
          )}

          {step === "done" && (
            <div className="py-16 text-center text-white space-y-8">
              <div className="relative w-24 h-24 mx-auto">
                <div className="absolute inset-0 bg-green-500/30 blur-3xl rounded-full animate-pulse"></div>
                <div className="relative p-7 bg-slate-800 rounded-[2rem] border border-green-500/50 flex items-center justify-center shadow-2xl">
                  <CheckCircle2 className="h-12 w-12 text-green-400" />
                </div>
              </div>
              <div className="space-y-3">
                <h3 className="text-2xl font-black">Knowledge Captured!</h3>
                <p className="text-sm text-zinc-500 max-w-[300px] mx-auto leading-relaxed">
                  {doneMessage}
                </p>
              </div>
            </div>
          )}

          {step === "error" && (
            <div className="py-12 text-center text-white space-y-8">
              <div className="relative w-20 h-20 mx-auto">
                <div className="absolute inset-0 bg-red-500/20 blur-2xl rounded-full"></div>
                <div className="relative p-5 bg-slate-800 rounded-[1.5rem] border border-red-500/30 flex items-center justify-center">
                  <AlertCircle className="h-10 w-10 text-red-400" />
                </div>
              </div>
              <div className="space-y-3">
                <h3 className="text-xl font-black">Connection Failed</h3>
                <p className="text-sm text-red-400/80 max-w-[320px] mx-auto leading-relaxed">
                  {errorMessage || "An unexpected error occurred. Please try again."}
                </p>
              </div>
              <button
                onClick={() => { setStep("setup"); setErrorMessage(""); }}
                className="px-8 py-4 rounded-2xl bg-zinc-800 text-white font-bold text-sm hover:bg-zinc-700 transition-colors"
              >
                Try Again
              </button>
            </div>
          )}
        </div>

        {/* Footer Info */}
        <div className="px-10 py-8 bg-white/[0.02] border-t border-white/5 flex flex-wrap items-center justify-center gap-6 text-[10px] font-black text-zinc-600 uppercase tracking-widest">
          <div className="flex items-center gap-2">
            <Shield className="w-3 h-3 text-green-500" />
            <span>SOC2 Certified</span>
          </div>
          <div className="h-1 w-1 rounded-full bg-zinc-800" />
          <div className="flex items-center gap-2">
            <Lock className="w-3 h-3 text-blue-500" />
            <span>AES-256 Bit</span>
          </div>
          <div className="h-1 w-1 rounded-full bg-zinc-800" />
          <div className="flex items-center gap-2">
            <CheckCircle2 className="w-3 h-3 text-primary" />
            <span>Zero Data Retention</span>
          </div>
        </div>
      </div>
    </div>
  );
}
