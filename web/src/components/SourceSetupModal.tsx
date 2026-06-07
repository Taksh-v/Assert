"use client";

import { useState, useEffect, useCallback } from "react";
import { X, Shield, Lock, Loader2, CheckCircle2, ChevronRight, Settings, AlertCircle, RefreshCw, Zap, Brain, UploadCloud, FileText } from "lucide-react";
import { apiFetch } from "@/lib/auth";
import { parseUTCDate } from "@/lib/date";
import ConnectorIcon from "./ConnectorIcon";

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
  size?: number;
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
  const [uploadProgress, setUploadProgress] = useState<Record<string, string>>({});
  const [isUploading, setIsUploading] = useState(false);
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

  const handleFileUploadConnectorCreation = useCallback(async () => {
    try {
      const response = await apiFetch(`/api/connectors`, {
        method: "POST",
        body: JSON.stringify({
          workspace_id: workspaceId,
          type: "file_upload",
          config: {},
        }),
      });
      if (response.ok) {
        const data = await response.json() as { id: string };
        setConnectorId(data.id);
        setStep("discover");
        await discoverResources(data.id);
        return data.id;
      } else {
        const errorData = await response.json();
        setErrorMessage(errorData.detail || "Failed to initialize upload area");
        setStep("error");
      }
    } catch (error) {
      console.error("Failed to create file_upload connector:", error);
      setErrorMessage("Failed to create file connector");
      setStep("error");
    }
    return null;
  }, [workspaceId, discoverResources]);

  const handleFileUpload = async (files: FileList) => {
    if (!connectorId) return;
    setIsUploading(true);
    setErrorMessage("");

    for (let i = 0; i < files.length; i++) {
      const file = files[i];
      if (file.size > 50 * 1024 * 1024) {
        setErrorMessage(`File ${file.name} exceeds maximum limit of 50MB`);
        setIsUploading(false);
        return;
      }

      const formData = new FormData();
      formData.append("file", file);

      setUploadProgress((prev) => ({ ...prev, [file.name]: "Uploading..." }));

      try {
        const response = await apiFetch(`/api/connectors/${connectorId}/upload`, {
          method: "POST",
          body: formData,
        });

        if (response.ok) {
          setUploadProgress((prev) => {
            const next = { ...prev };
            delete next[file.name];
            return next;
          });
        } else {
          const errorData = await response.json();
          setErrorMessage(`Failed to upload ${file.name}: ${errorData.detail || "Unknown error"}`);
          setUploadProgress((prev) => ({ ...prev, [file.name]: "Failed" }));
          setIsUploading(false);
          return;
        }
      } catch (error) {
        console.error("Upload failed:", error);
        setErrorMessage(`Network error uploading ${file.name}`);
        setUploadProgress((prev) => ({ ...prev, [file.name]: "Failed" }));
        setIsUploading(false);
        return;
      }
    }
    
    setIsUploading(false);
    await discoverResources(connectorId);
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
            (type === "file_upload" || c.config_summary?.oauth || c.config_summary?.direct_token)
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
      const found = await checkForExistingConnector();
      if (!found && type === "file_upload") {
        await handleFileUploadConnectorCreation();
      }
      setIsInitialLoading(false);
    };
    void init();
  }, [checkForExistingConnector, type, handleFileUploadConnectorCreation]);

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
        onConnect(config);
        onClose();
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
      const date = parseUTCDate(isoString);
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
    <div className="fixed inset-0 z-[100] flex items-center justify-center bg-black/60 p-6 backdrop-blur-md">
      <div className="w-full max-w-2xl overflow-hidden rounded-3xl border border-slate-800 bg-slate-950 shadow-2xl">
        <div className="flex items-center justify-between border-b border-slate-800 bg-slate-900/40 p-6 md:p-8">
          <div className="flex items-center gap-4">
            <div className="flex h-12 w-12 items-center justify-center rounded-xl border border-slate-800 bg-slate-900 text-slate-100">
              <ConnectorIcon type={type} className="h-6 w-6" />
            </div>
            <div>
              <h2 className="text-xl font-semibold tracking-tight text-slate-100">Connect {metadata.name}</h2>
              <p className="mt-0.5 font-mono text-[9px] uppercase tracking-wider text-slate-500">
                {step === "setup" && "Secure authorization"}
                {step === "discover" && "Browsing your knowledge"}
                {step === "syncing" && "Indexing your workspace"}
                {step === "done" && "All set"}
                {step === "error" && "Something went wrong"}
              </p>
            </div>
          </div>
          <button
            onClick={onClose}
            className="flex h-9 w-9 items-center justify-center rounded-full border border-slate-800 bg-slate-900 text-slate-400 hover:text-slate-100 hover:border-slate-700 transition"
          >
            <X className="h-4 w-4" />
          </button>
        </div>

        <div className="p-6 md:p-8">
          {isInitialLoading ? (
            <div className="flex flex-col items-center justify-center py-16 gap-3">
              <Loader2 className="h-8 w-8 animate-spin text-blue-500" />
              <p className="font-mono text-[9px] uppercase tracking-wider text-slate-500">Validating connection</p>
            </div>
          ) : step === "setup" ? (
            <div className="space-y-6">
              <div className="flex flex-col items-center space-y-3 py-2 text-center">
                <style dangerouslySetInnerHTML={{__html: `
                  @keyframes bridge-flow {
                    0% { transform: translateX(-100%); }
                    100% { transform: translateX(300%); }
                  }
                `}} />
                <div className="flex items-center justify-center gap-5 py-4 w-full">
                  <div className="flex h-14 w-14 shrink-0 items-center justify-center rounded-2xl border border-slate-800 bg-slate-900 shadow-md">
                    <Brain className="h-6 w-6 text-blue-500 animate-pulse" />
                  </div>
                  
                  <div className="relative w-20 h-[3px] bg-slate-800 rounded-full overflow-hidden shrink-0">
                    <div className="absolute inset-0 overflow-hidden">
                      <div 
                        className="h-full w-8 bg-gradient-to-r from-transparent via-blue-400 to-transparent"
                        style={{
                          animation: "bridge-flow 1.5s infinite linear",
                        }}
                      />
                    </div>
                  </div>

                  <div className="flex h-14 w-14 shrink-0 items-center justify-center rounded-2xl border border-slate-800 bg-slate-900 shadow-md">
                    <ConnectorIcon type={type} className="h-6 w-6" />
                  </div>
                </div>
                <h3 className="text-lg font-semibold tracking-tight text-slate-100">
                  {hasDirectToken ? "Direct connection" : "One-click authorization"}
                </h3>
                <p className="max-w-[340px] text-sm leading-relaxed text-slate-400">
                  {type === "slack" && hasDirectToken
                    ? "Your Slack bot token is already configured. Connect instantly and start indexing channels."
                    : "Authorize Assest to access your files securely. No tokens or manual configuration required."}
                </p>
              </div>

              {errorMessage && (
                <div className="flex items-center gap-3 rounded-xl border border-rose-950 bg-rose-950/20 p-4 text-rose-400">
                  <AlertCircle className="h-5 w-5 shrink-0" />
                  <p className="text-sm">{errorMessage}</p>
                </div>
              )}

              <button
                onClick={handleOAuth}
                disabled={isLoading}
                className="flex h-12 w-full items-center justify-center gap-2 rounded-xl bg-blue-600 px-5 text-sm font-semibold text-white transition hover:bg-blue-500 disabled:cursor-not-allowed disabled:opacity-50"
              >
                {isLoading ? (
                  <Loader2 className="h-5 w-5 animate-spin" />
                ) : (
                  <>
                    <ConnectorIcon type={type} className="h-5 w-5 shrink-0" />
                    <span>{type === "slack" && hasDirectToken ? "Connect Slack" : `Authorize ${metadata.name}`}</span>
                    <ChevronRight className="h-4 w-4" />
                  </>
                )}
              </button>

              <div className="flex flex-col items-center gap-4 pt-1">
                <button
                  onClick={() => setShowAdvanced(!showAdvanced)}
                  className="inline-flex items-center gap-2 font-mono text-[9px] uppercase tracking-wider text-slate-500 transition hover:text-slate-300"
                >
                  <Settings className="h-3.5 w-3.5" />
                  {showAdvanced ? "Hide advanced setup" : "Manual token setup"}
                </button>

                {showAdvanced && (
                  <div className="w-full space-y-3 animate-fade-in">
                    <input
                      type="password"
                      placeholder={
                        type === "notion"
                          ? "Enter Notion integration token..."
                          : type === "google_drive"
                            ? "Paste OAuth access token..."
                            : "Enter Slack bot token..."
                      }
                      className="h-12 w-full rounded-xl border border-slate-800 bg-slate-900/50 px-4 text-sm text-slate-100 placeholder:text-slate-600 focus:border-slate-700 focus:outline-none transition"
                      onChange={(e) => setConfig({ ...config, api_key: e.target.value })}
                    />
                    <button
                      onClick={handleManualToken}
                      disabled={isLoading || !config.api_key}
                      className="flex h-12 w-full items-center justify-center rounded-xl border border-slate-800 bg-slate-900 text-sm font-semibold text-slate-100 transition hover:bg-slate-800 disabled:cursor-not-allowed disabled:opacity-50"
                    >
                      {isLoading ? <Loader2 className="h-5 w-5 animate-spin" /> : "Verify manual connection"}
                    </button>
                  </div>
                )}
              </div>
            </div>
          ) : step === "discover" ? (
            <div className="space-y-4">
              <div className="flex flex-col gap-2 border-b border-slate-800 pb-3 sm:flex-row sm:items-center sm:justify-between">
                <div>
                  <h3 className="text-base font-semibold tracking-tight text-slate-100">
                    {type === "file_upload" ? "Upload and manage files" : "Pick your knowledge"}
                  </h3>
                  <p className="text-xs text-slate-400">
                    {type === "file_upload" 
                      ? "Ingest local files directly into the reasoning workspace."
                      : "Choose which spaces should be indexed for grounded answers."}
                  </p>
                </div>
                {type !== "file_upload" && (
                  <div className="flex items-center gap-3">
                    <button
                      onClick={toggleSelectAll}
                      className="font-mono text-[9px] uppercase tracking-wider text-blue-400 transition hover:text-blue-300"
                    >
                      {selectedIds.length === discoveredItems.length ? "Deselect all" : "Select all"}
                    </button>
                    <span className="rounded-full border border-slate-800 bg-slate-900 px-2.5 py-0.5 font-mono text-[9px] text-slate-300">
                      {selectedIds.length} / {discoveredItems.length}
                    </span>
                  </div>
                )}
              </div>

              {type === "file_upload" && (
                <div className="space-y-3">
                  <div 
                    className={`border border-dashed border-slate-800 rounded-2xl p-7 bg-slate-900/10 hover:bg-slate-900/20 hover:border-slate-700 transition text-center cursor-pointer relative flex flex-col items-center justify-center gap-2 ${
                      isUploading ? "pointer-events-none opacity-55" : ""
                    }`}
                  >
                    <input
                      type="file"
                      multiple
                      className="absolute inset-0 opacity-0 cursor-pointer"
                      onChange={async (e) => {
                        if (e.target.files && e.target.files.length > 0) {
                          await handleFileUpload(e.target.files);
                        }
                      }}
                      disabled={isUploading}
                    />
                    <UploadCloud className="h-6 w-6 text-slate-500 animate-pulse" />
                    <p className="text-xs text-slate-300 font-semibold">
                      Drag & drop files here, or click to browse
                    </p>
                    <p className="text-[10px] text-slate-500 font-mono">
                      Max 50MB. Supports PDF, plain text, HTML, images (OCR), audio/video
                    </p>
                  </div>

                  {errorMessage && (
                    <div className="flex items-center gap-3 rounded-xl border border-rose-950 bg-rose-950/20 p-4 text-rose-400">
                      <AlertCircle className="h-5 w-5 shrink-0" />
                      <p className="text-sm">{errorMessage}</p>
                    </div>
                  )}

                  {Object.entries(uploadProgress).map(([name, status]) => (
                    <div key={name} className="flex items-center justify-between p-3 rounded-xl border border-slate-800 bg-slate-900/40 animate-pulse">
                      <div className="flex items-center gap-3">
                        <Loader2 className="h-3.5 w-3.5 animate-spin text-blue-400" />
                        <span className="text-xs text-slate-300 font-medium truncate max-w-[200px]">{name}</span>
                      </div>
                      <span className="text-[9px] font-mono uppercase text-slate-500">{status}</span>
                    </div>
                  ))}
                </div>
              )}

              <div className="max-h-[250px] space-y-2 overflow-y-auto pr-1">
                {isDiscovering ? (
                  <div className="flex flex-col items-center justify-center py-16 gap-3">
                    <Loader2 className="h-8 w-8 animate-spin text-blue-500" />
                    <p className="font-mono text-[9px] uppercase tracking-wider text-slate-500">Scanning workspace</p>
                  </div>
                ) : discoveredItems.length === 0 ? (
                  <div className="flex flex-col items-center justify-center py-16 gap-3 rounded-2xl border border-dashed border-slate-800 bg-slate-950">
                    {type === "file_upload" ? (
                      <>
                        <FileText className="h-8 w-8 text-slate-700" />
                        <p className="font-mono text-[9px] uppercase tracking-wider text-slate-500">No files uploaded yet</p>
                        <p className="max-w-[280px] text-center text-xs text-slate-400">
                          Upload files to connect them to the system.
                        </p>
                      </>
                    ) : (
                      <>
                        <AlertCircle className="h-8 w-8 text-slate-600" />
                        <p className="font-mono text-[9px] uppercase tracking-wider text-slate-500">No resources found</p>
                        <p className="max-w-[280px] text-center text-xs text-slate-400">
                          Make sure the workspace content has been shared with the integration.
                        </p>
                      </>
                    )}
                  </div>
                ) : (
                  discoveredItems.map((item) => {
                    const selected = selectedIds.includes(item.id);
                    return (
                      <button
                        key={item.id}
                        onClick={() => {
                          if (selected) setSelectedIds(selectedIds.filter((id) => id !== item.id));
                          else setSelectedIds([...selectedIds, item.id]);
                        }}
                        className={`flex w-full items-center gap-4 rounded-xl border p-4.5 text-left transition ${
                          selected
                            ? "border-blue-500/50 bg-blue-950/20 text-slate-100 hover:border-blue-500 hover:bg-blue-950/30"
                            : "border-slate-800 bg-slate-900/30 hover:border-slate-700 hover:bg-slate-900/50"
                        }`}
                      >
                        <div
                          className={`flex h-5 w-5 shrink-0 items-center justify-center rounded border transition ${
                            selected ? "border-blue-500 bg-blue-500 text-white" : "border-slate-700 bg-transparent"
                          }`}
                        >
                          {selected ? <CheckCircle2 className="h-3.5 w-3.5" /> : null}
                        </div>
                        <div className="min-w-0 flex-1">
                          <div className="flex items-center gap-2">
                            {type === "file_upload" ? (
                              <FileText className="h-3.5 w-3.5 text-blue-400 shrink-0" />
                            ) : item.icon ? (
                              <span className="text-sm shrink-0">{item.icon}</span>
                            ) : null}
                            <p className={`truncate text-sm font-semibold ${selected ? "text-blue-400" : "text-slate-200"}`}>
                              {item.name}
                            </p>
                          </div>
                          <div className="mt-1 flex flex-wrap items-center gap-2">
                            <span className="rounded border border-slate-800 bg-slate-950 px-1.5 py-0.5 font-mono text-[8px] uppercase tracking-wider text-slate-400">
                              {item.display_type || item.type}
                            </span>
                            {item.last_modified ? (
                              <span className="font-mono text-[8px] text-slate-500">{formatTimeAgo(item.last_modified)}</span>
                            ) : null}
                            {item.size !== undefined ? (
                              <span className="font-mono text-[8px] text-slate-500">{(item.size / 1024).toFixed(1)} KB</span>
                            ) : null}
                            {item.member_count !== undefined && item.member_count > 0 ? (
                              <span className="font-mono text-[8px] text-slate-500">{item.member_count} members</span>
                            ) : null}
                          </div>
                        </div>
                      </button>
                    );
                  })
                )}
              </div>

              {!isDiscovering && discoveredItems.length > 0 ? (
                <button
                  onClick={handleSync}
                  className="flex h-12 w-full items-center justify-center gap-2 rounded-xl bg-blue-600 text-sm font-semibold text-white transition hover:bg-blue-500"
                >
                  <span>{selectedIds.length > 0 ? `Sync ${selectedIds.length} selected` : "Sync all knowledge"}</span>
                  <CheckCircle2 className="h-4 w-4" />
                </button>
              ) : null}
            </div>
          ) : step === "syncing" ? (
            <div className="py-12 text-center space-y-4">
              <div className="relative mx-auto h-20 w-20">
                <div className="absolute inset-0 rounded-full bg-blue-500/10 blur-xl" />
                <div className="relative flex h-20 w-20 items-center justify-center rounded-2xl border border-slate-800 bg-slate-900 shadow-xl">
                  <RefreshCw className="h-10 w-10 animate-spin text-blue-500" style={{ animationDuration: "3s" }} />
                </div>
              </div>
              <div className="space-y-2">
                <h3 className="text-lg font-semibold tracking-tight text-slate-100">Ingesting knowledge</h3>
                <p className="mx-auto max-w-[320px] text-xs text-slate-400">
                  {syncProgress || "Processing documents through the ingestion pipeline."}
                </p>
              </div>
            </div>
          ) : step === "done" ? (
            <div className="py-12 text-center space-y-4">
              <div className="relative mx-auto h-20 w-20">
                <div className="absolute inset-0 rounded-full bg-emerald-500/10 blur-xl" />
                <div className="relative flex h-20 w-20 items-center justify-center rounded-2xl border border-slate-800 bg-slate-900 shadow-xl">
                  <CheckCircle2 className="h-10 w-10 text-emerald-500" />
                </div>
              </div>
              <div className="space-y-2">
                <h3 className="text-lg font-semibold tracking-tight text-slate-100">Knowledge captured</h3>
                <p className="mx-auto max-w-[320px] text-xs text-slate-400">{doneMessage}</p>
              </div>
            </div>
          ) : (
            <div className="py-8 text-center space-y-4">
              <div className="relative mx-auto h-16 w-16">
                <div className="absolute inset-0 rounded-full bg-rose-500/10 blur-xl" />
                <div className="relative flex h-16 w-16 items-center justify-center rounded-2xl border border-slate-800 bg-slate-900 shadow-xl">
                  <AlertCircle className="h-8 w-8 text-rose-500" />
                </div>
              </div>
              <div className="space-y-2">
                <h3 className="text-base font-semibold tracking-tight text-slate-100">Connection failed</h3>
                <p className="mx-auto max-w-[340px] text-xs text-rose-400">
                  {errorMessage || "An unexpected error occurred. Please try again."}
                </p>
              </div>
              <button
                onClick={() => {
                  setStep("setup");
                  setErrorMessage("");
                }}
                className="inline-flex items-center justify-center rounded-full bg-slate-900 px-5 py-2 text-xs font-semibold text-slate-200 border border-slate-800 hover:bg-slate-800 transition"
              >
                Try again
              </button>
            </div>
          )}
        </div>
      </div>
    </div>
  );
}
