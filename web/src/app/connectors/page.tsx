"use client";

import { useState, useEffect, useMemo, useCallback } from "react";
import { useSearchParams } from "next/navigation";
import { 
  Search,
  Settings2, 
  Zap,
  ShieldCheck,
  Trash2,
  Clock,
  CheckCircle2,
  AlertCircle,
  RefreshCw,
} from "lucide-react";

import SourceSetupModal from "@/components/SourceSetupModal";
import { apiFetch, getActiveWorkspace } from "@/lib/auth";

const API_URL = process.env.NEXT_PUBLIC_API_URL || "http://localhost:8000";

interface Connector {
  id: string;
  name: string;
  type: string;
  status: "active" | "inactive" | "error" | "pending";
  last_synced_at?: string;
  config_summary?: Record<string, unknown>;
  document_count?: number;
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
    description: "Sync pages, databases, and enterprise workspaces.",
    color: "#000000",
    icon: "N",
  },
  google_drive: {
    name: "Google Drive",
    category: "Cloud Storage",
    description: "Securely index Docs, Sheets, and company PDFs.",
    color: "#4285F4",
    icon: "G",
  },
  slack: {
    name: "Slack",
    category: "Communication",
    description: "Capture organizational knowledge from public channels.",
    color: "#4A154B",
    icon: "S",
  },
  github: {
    name: "GitHub",
    category: "Engineering",
    description: "Index documentation, issues, and READMEs.",
    color: "#181717",
    icon: "H",
  }
};

// Persistent session cache
let globalConnectorsCache: Connector[] | null = null;

export default function ConnectorsPage() {
  const searchParams = useSearchParams();
  const [connectors, setConnectors] = useState<Connector[]>(globalConnectorsCache || []);
  const [isLoading, setIsLoading] = useState(!globalConnectorsCache);
  const [searchQuery, setSearchQuery] = useState("");
  const [selectedCategory, setSelectedCategory] = useState("All");
  const [setupSource, setSetupSource] = useState<string | null>(null);
  const [notification, setNotification] = useState<{ type: "success" | "error"; message: string } | null>(null);

  const fetchConnectors = useCallback(async () => {
    try {
      const activeWs = getActiveWorkspace();
      const workspaceId = activeWs?.id || "default-workspace";
      const response = await apiFetch(`/api/connectors?workspace_id=${workspaceId}`);
      if (response.ok) {
        const data = await response.json() as Connector[];
        setConnectors(data);
        globalConnectorsCache = data;
      }
    } catch (error) {
      console.error("Failed to fetch connectors:", error);
    } finally {
      setIsLoading(false);
    }
  }, []);

  // Handle OAuth redirect params (from callback page fallback)
  useEffect(() => {
    const connected = searchParams.get("connected");
    const connectorId = searchParams.get("connector_id");

    if (connected && connectorId) {
      setNotification({ type: "success", message: `Successfully connected to ${CONNECTOR_METADATA[connected]?.name || connected}!` });
      fetchConnectors();
      // Clean URL
      window.history.replaceState({}, "", "/connectors");
    }
  }, [searchParams, fetchConnectors]);

  useEffect(() => {
    void fetchConnectors();
  }, [fetchConnectors]);

  // Auto-dismiss notifications
  useEffect(() => {
    if (notification) {
      const timer = setTimeout(() => setNotification(null), 5000);
      return () => clearTimeout(timer);
    }
  }, [notification]);

  const disconnectConnector = async (connectorId: string, connectorType: string) => {
    try {
      const response = await apiFetch(`/api/connectors/${connectorId}`, { method: "DELETE" });
      if (response.ok) {
        setNotification({ type: "success", message: `${CONNECTOR_METADATA[connectorType]?.name || connectorType} disconnected` });
        await fetchConnectors();
      }
    } catch (error) {
      console.error("Failed to disconnect:", error);
      setNotification({ type: "error", message: "Failed to disconnect connector" });
    }
  };

  const resyncConnector = async (connectorId: string) => {
    try {
      const response = await apiFetch(`/api/connectors/${connectorId}/sync`, {
        method: "POST",
        body: JSON.stringify({}),
      });
      if (response.ok) {
        setNotification({ type: "success", message: "Sync completed successfully!" });
        await fetchConnectors();
      } else {
        setNotification({ type: "error", message: "Sync failed. Check backend logs." });
      }
    } catch {
      setNotification({ type: "error", message: "Failed to trigger sync" });
    }
  };

  const formatLastSync = (isoString?: string) => {
    if (!isoString) return "Never";
    try {
      const date = new Date(isoString);
      const now = new Date();
      const diffMs = now.getTime() - date.getTime();
      const diffMins = Math.floor(diffMs / 60000);
      if (diffMins < 1) return "Just now";
      if (diffMins < 60) return `${diffMins}m ago`;
      const diffHours = Math.floor(diffMins / 60);
      if (diffHours < 24) return `${diffHours}h ago`;
      const diffDays = Math.floor(diffHours / 24);
      return `${diffDays}d ago`;
    } catch {
      return "Unknown";
    }
  };

  const filteredConnectors = useMemo(() => {
    return Object.keys(CONNECTOR_METADATA).filter(type => {
      const meta = CONNECTOR_METADATA[type];
      const matchesSearch = meta.name.toLowerCase().includes(searchQuery.toLowerCase()) || 
                           meta.description.toLowerCase().includes(searchQuery.toLowerCase());
      const matchesCategory = selectedCategory === "All" || meta.category === selectedCategory;
      return matchesSearch && matchesCategory;
    });
  }, [searchQuery, selectedCategory]);

  return (
    <div className="flex-1 h-full bg-background overflow-y-auto relative custom-scrollbar">
      {/* Premium Background Atmosphere */}
      <div className="absolute top-0 left-0 right-0 h-[500px] bg-gradient-to-b from-blue-600/5 via-transparent to-transparent pointer-events-none" />
      <div className="absolute top-20 right-20 h-64 w-64 bg-blue-500/10 rounded-full blur-[120px] pointer-events-none animate-pulse" />

      {/* Notification Toast */}
      {notification && (
        <div className={`fixed top-6 right-6 z-[200] flex items-center gap-3 px-6 py-4 rounded-2xl shadow-2xl border backdrop-blur-xl animate-in slide-in-from-top-4 duration-300 ${
          notification.type === "success"
            ? "bg-green-500/10 border-green-500/20 text-green-400"
            : "bg-red-500/10 border-red-500/20 text-red-400"
        }`}>
          {notification.type === "success" ? (
            <CheckCircle2 className="w-5 h-5" />
          ) : (
            <AlertCircle className="w-5 h-5" />
          )}
          <span className="text-sm font-bold">{notification.message}</span>
        </div>
      )}

      <div className="max-w-7xl mx-auto p-12 space-y-12 relative z-10">
        {/* Header Section */}
        <div className="flex flex-col md:flex-row md:items-end justify-between gap-8">
          <div className="space-y-4">
            <div className="inline-flex items-center gap-2 px-3 py-1 rounded-full bg-blue-500/10 border border-blue-500/20 text-[10px] font-black uppercase tracking-widest text-blue-400">
              <ShieldCheck className="w-3 h-3" />
              Live Enterprise Connectors
            </div>
            <h1 className="text-6xl font-black tracking-tighter leading-none">
              Knowledge <span className="text-zinc-600">Silos</span><br/>
              <span className="gradient-text">Unified.</span>
            </h1>
          </div>

          {/* Search & Filter Bar */}
          <div className="flex items-center gap-4 bg-white/5 p-2 rounded-2xl border border-white/10 backdrop-blur-md w-full max-w-md shadow-2xl">
            <div className="flex-1 flex items-center gap-3 px-4">
              <Search className="w-4 h-4 text-zinc-500" />
              <input 
                type="text" 
                placeholder="Search sources..." 
                className="bg-transparent border-none text-sm text-white focus:outline-none w-full font-medium"
                value={searchQuery}
                onChange={(e) => setSearchQuery(e.target.value)}
              />
            </div>
            <div className="h-8 w-[1px] bg-white/10" />
            <select 
              className="bg-transparent text-xs font-bold text-zinc-400 px-4 focus:outline-none cursor-pointer hover:text-white transition-colors"
              value={selectedCategory}
              onChange={(e) => setSelectedCategory(e.target.value)}
            >
              <option>All</option>
              <option>Productivity</option>
              <option>Cloud Storage</option>
              <option>Communication</option>
              <option>Engineering</option>
            </select>
          </div>
        </div>

        {/* Content Grid */}
        {isLoading ? (
          <div className="grid grid-cols-1 md:grid-cols-2 lg:grid-cols-3 xl:grid-cols-4 gap-6">
            {[1, 2, 3, 4].map((i) => (
              <div key={i} className="h-72 rounded-[2rem] bg-white/5 animate-pulse border border-white/5" />
            ))}
          </div>
        ) : (
          <div className="grid grid-cols-1 md:grid-cols-2 lg:grid-cols-3 xl:grid-cols-4 gap-6">
            {filteredConnectors.map((type) => {
              const meta = CONNECTOR_METADATA[type];
              const instance = connectors.find(c => c.type === type);
              const isActive = instance?.status === "active";
              const isError = instance?.status === "error";
              const workspaceName = instance?.config_summary?.workspace_name || instance?.config_summary?.team_name;

              return (
                <div 
                  key={type} 
                  className="glass-card group relative flex flex-col p-8 hover:-translate-y-2 transition-all duration-500 border-white/5 hover:border-white/20"
                >
                  <div className="flex items-start justify-between">
                    <div 
                      className="h-14 w-14 rounded-2xl flex items-center justify-center text-xl font-black text-white shadow-2xl transition-transform group-hover:scale-110 duration-500"
                      style={{ backgroundColor: meta.color, boxShadow: `0 10px 30px ${meta.color}44` }}
                    >
                      {meta.icon}
                    </div>
                    
                    <div className={`flex items-center gap-2 px-3 py-1 rounded-full text-[9px] font-black uppercase tracking-widest ${
                      isActive 
                        ? "bg-green-500/10 text-green-400 border border-green-500/20 shadow-[0_0_15px_rgba(34,197,94,0.2)]" 
                        : isError
                        ? "bg-red-500/10 text-red-400 border border-red-500/20"
                        : "bg-zinc-800/50 text-zinc-600 border border-white/5"
                    }`}>
                      {isActive ? (
                        <>
                          <div className="h-1.5 w-1.5 rounded-full bg-green-500 animate-pulse" />
                          Connected
                        </>
                      ) : isError ? (
                        <>
                          <div className="h-1.5 w-1.5 rounded-full bg-red-500" />
                          Error
                        </>
                      ) : (
                        "Ready"
                      )}
                    </div>
                  </div>

                  <div className="mt-8 space-y-2">
                    <div className="flex items-center justify-between">
                      <h3 className="text-lg font-bold text-white group-hover:text-blue-400 transition-colors">{meta.name}</h3>
                      <span className="text-[8px] font-black text-zinc-600 uppercase tracking-widest">{meta.category}</span>
                    </div>
                    <p className="text-xs text-zinc-500 font-medium leading-relaxed line-clamp-2">
                      {meta.description}
                    </p>
                    {workspaceName && (
                      <p className="text-[10px] text-blue-400/60 font-bold truncate">
                        {String(workspaceName)}
                      </p>
                    )}
                  </div>

                  <div className="mt-auto pt-8 flex items-center justify-between">
                    <div className="flex flex-col">
                      <span className="text-[9px] font-black text-zinc-600 uppercase tracking-tighter">
                        {isActive ? "Last Sync" : "Status"}
                      </span>
                      <span className="text-[10px] font-bold text-zinc-400 flex items-center gap-1">
                        {isActive ? (
                          <>
                            <Clock className="w-3 h-3" />
                            {formatLastSync(instance?.last_synced_at)}
                          </>
                        ) : (
                          "Not Setup"
                        )}
                      </span>
                    </div>
                    
                    <div className="flex items-center gap-2">
                      {isActive && (
                        <>
                          <button 
                            onClick={(e) => { e.stopPropagation(); resyncConnector(instance!.id); }}
                            className="h-10 w-10 rounded-xl bg-zinc-800 hover:bg-zinc-700 flex items-center justify-center transition-colors border border-white/5"
                            title="Re-sync"
                          >
                            <RefreshCw className="w-3.5 h-3.5 text-zinc-400" />
                          </button>
                          <button 
                            onClick={(e) => { e.stopPropagation(); disconnectConnector(instance!.id, type); }}
                            className="h-10 w-10 rounded-xl bg-zinc-800 hover:bg-red-500/20 flex items-center justify-center transition-colors border border-white/5 hover:border-red-500/30"
                            title="Disconnect"
                          >
                            <Trash2 className="w-3.5 h-3.5 text-zinc-400 hover:text-red-400" />
                          </button>
                        </>
                      )}
                      <button 
                        onClick={() => setSetupSource(type)}
                        className={`h-10 px-6 rounded-xl text-[10px] font-black uppercase tracking-widest transition-all duration-300 flex items-center gap-2 ${
                          isActive
                            ? "bg-zinc-800 hover:bg-zinc-700 text-zinc-300 border border-white/5"
                            : "bg-white text-black hover:bg-blue-500 hover:text-white shadow-xl shadow-white/5"
                        }`}
                      >
                        {isActive ? (
                          <>
                            <Settings2 className="w-3.5 h-3.5" />
                            Manage
                          </>
                        ) : (
                          <>
                            <Zap className="w-3.5 h-3.5" />
                            Connect
                          </>
                        )}
                      </button>
                    </div>
                  </div>
                </div>
              );
            })}
          </div>
        )}

        {/* Pro Security Footer */}
        <div className="bg-white/[0.02] border border-white/5 rounded-[2.5rem] p-12 flex flex-col md:flex-row items-center justify-between gap-12 relative overflow-hidden group">
           <div className="absolute top-0 left-0 w-full h-full bg-gradient-to-r from-blue-500/[0.03] to-transparent opacity-0 group-hover:opacity-100 transition-opacity duration-1000" />
           <div className="space-y-6 relative z-10">
              <div className="flex items-center gap-4">
                 <div className="h-12 w-12 rounded-2xl bg-zinc-900 border border-white/10 flex items-center justify-center">
                    <ShieldCheck className="w-6 h-6 text-blue-500" />
                 </div>
                 <h2 className="text-2xl font-black tracking-tight">Enterprise Trust Engine</h2>
              </div>
              <p className="text-sm text-zinc-500 font-medium max-w-xl leading-relaxed">
                 Assest Brain uses hardware-level encryption and zero-knowledge indexing. Your raw data never leaves your environment; only vectorized semantic intelligence is stored.
              </p>
           </div>
           <div className="flex gap-8 items-center relative z-10">
              <div className="text-center">
                 <p className="text-2xl font-black text-white">256</p>
                 <p className="text-[9px] font-black text-zinc-600 uppercase tracking-widest">AES Bits</p>
              </div>
              <div className="h-10 w-[1px] bg-white/10" />
              <div className="text-center">
                 <p className="text-2xl font-black text-white">SOC2</p>
                 <p className="text-[9px] font-black text-zinc-600 uppercase tracking-widest">Compliance</p>
              </div>
              <div className="h-10 w-[1px] bg-white/10" />
              <div className="text-center">
                 <p className="text-2xl font-black text-white">{connectors.filter(c => c.status === "active").length}</p>
                 <p className="text-[9px] font-black text-zinc-600 uppercase tracking-widest">Active</p>
              </div>
           </div>
        </div>
      </div>

      {setupSource && (
        <SourceSetupModal 
          type={setupSource}
          metadata={CONNECTOR_METADATA[setupSource]}
          workspaceId={getActiveWorkspace()?.id || "default-workspace"}
          onClose={() => setSetupSource(null)}
          onConnect={() => { fetchConnectors(); setNotification({ type: "success", message: "Connector synced successfully!" }); }}
        />
      )}
    </div>
  );
}
