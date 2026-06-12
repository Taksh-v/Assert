"use client";

import React, { useState, useEffect, useCallback } from "react";
import Link from "next/link";
import { usePathname, useRouter } from "next/navigation";
import { MessageSquare, Link2, Brain, Plus, Trash2, Home, BarChart3, LogOut, ChevronDown } from "lucide-react";
import { apiFetch, getActiveWorkspace, getCurrentUser, isAdminWorkspaceRole, signOut, AUTH_CHANGE_EVENT } from "@/lib/auth";

interface Conversation {
  id: string;
  title: string;
  created_at: string;
  updated_at: string;
}

export const CONVERSATIONS_CHANGE_EVENT = "assest_conversations_change";

export default function Sidebar() {
  const pathname = usePathname();
  const router = useRouter();
  const [conversations, setConversations] = useState<Conversation[]>([]);
  const [loading, setLoading] = useState(false);
  const [showProfileMenu, setShowProfileMenu] = useState(false);
  const [user, setUser] = useState(getCurrentUser());
  const [workspace, setWorkspace] = useState(getActiveWorkspace());
  
  const workspaceId = workspace?.id;
  const isAdmin = isAdminWorkspaceRole(workspace?.role);
  
  const initials = user?.full_name 
    ? user.full_name.split(" ").map(n => n[0]).join("").toUpperCase().slice(0, 2)
    : user?.email ? user.email.slice(0, 2).toUpperCase() : "US";

  // Listen for auth/workspace changes
  useEffect(() => {
    const handleAuthChange = () => {
      setUser(getCurrentUser());
      setWorkspace(getActiveWorkspace());
    };
    window.addEventListener(AUTH_CHANGE_EVENT, handleAuthChange);
    return () => window.removeEventListener(AUTH_CHANGE_EVENT, handleAuthChange);
  }, []);

  // Add click outside listener
  useEffect(() => {
    const handleClickOutside = (e: MouseEvent) => {
      const target = e.target as HTMLElement;
      if (!target.closest('.profile-menu-container')) {
        setShowProfileMenu(false);
      }
    };
    if (showProfileMenu) document.addEventListener('click', handleClickOutside);
    return () => document.removeEventListener('click', handleClickOutside);
  }, [showProfileMenu]);

  const handleSignOut = () => {
    setShowProfileMenu(false);
    void signOut();
  };

  const fetchConversations = useCallback(async () => {
    if (!workspaceId) {
      setConversations([]);
      return;
    }

    // Only show loading if we have no conversations yet
    if (conversations.length === 0) {
      setLoading(true);
    }

    try {
      const response = await apiFetch(`/api/conversations?workspace_id=${workspaceId}`);
      if (response.ok) {
        const data = await response.json();
        setConversations(data);
      }
    } catch (error) {
      console.error("Failed to fetch conversations in sidebar:", error);
    } finally {
      setLoading(false);
    }
  }, [workspaceId, conversations.length]);

  useEffect(() => {
    queueMicrotask(() => void fetchConversations());

    const handleUpdate = () => {
      void fetchConversations();
    };

    window.addEventListener(CONVERSATIONS_CHANGE_EVENT, handleUpdate);
    return () => {
      window.removeEventListener(CONVERSATIONS_CHANGE_EVENT, handleUpdate);
    };
  }, [fetchConversations]);

  const handleDelete = async (e: React.MouseEvent, id: string) => {
    e.preventDefault();
    e.stopPropagation();
    if (!confirm("Are you sure you want to delete this chat thread?")) return;

    try {
      const response = await apiFetch(`/api/conversations/${id}`, {
        method: "DELETE",
      });
      if (response.ok) {
        // Notify changes
        window.dispatchEvent(new Event(CONVERSATIONS_CHANGE_EVENT));
        // If we are currently on the deleted chat, redirect to home
        if (pathname === `/chat/${id}`) {
          router.push("/");
        }
      }
    } catch (error) {
      console.error("Failed to delete conversation:", error);
    }
  };



  return (
    <div className="flex h-screen w-60 flex-col border-r border-[var(--border-subtle)] bg-[var(--bg-sidebar)] text-[var(--text-secondary)] select-none relative z-20 font-mono text-[11px] tracking-tight">
      {/* Brand & Logo (Top) */}
      <div className="flex flex-col p-4 border-b border-[var(--border-subtle)] bg-[var(--bg-sidebar)] relative">
        <div className="flex items-center gap-2.5">
          <div className="flex h-6 w-6 items-center justify-center rounded bg-[var(--accent-muted)] border border-[var(--accent)]/20 shadow-[0_0_12px_rgba(99,102,241,0.15)] animate-pulse-ring">
            <Brain className="h-3.5 w-3.5 text-[var(--accent)]" />
          </div>
          <span className="text-[10px] font-bold tracking-widest text-[var(--text-primary)] font-display uppercase">Assest Engine</span>
        </div>
      </div>

      {/* Categorized Operational Folders */}
      <div className="px-3 pt-4 space-y-4 flex-1 overflow-y-auto scrollbar-thin">
        {/* Section 1: Core Operations */}
        <div className="space-y-1">
          <span className="label-caps text-[9px] text-[var(--text-muted)] px-3 block mb-1.5 font-bold">Core Operations</span>
          <Link
            href="/"
            className={`flex items-center justify-between rounded-lg px-3 py-2 transition-all duration-250 ease-[cubic-bezier(0.16,1,0.3,1)] ${
              pathname === "/" || pathname.startsWith("/chat")
                ? "bg-[var(--bg-surface-hover)] text-[var(--text-primary)] border border-[var(--border-focus)] shadow-[var(--shadow-glow)] pl-[12px]"
                : "text-[var(--text-secondary)] hover:bg-[var(--bg-surface)]/40 hover:text-[var(--text-primary)] hover:translate-x-0.5"
            }`}
          >
            <div className="flex items-center gap-2.5">
              <Home className="h-3.5 w-3.5 text-[var(--accent)]" />
              <span className="uppercase tracking-wider font-semibold">Composer</span>
            </div>
            <span className="text-[8px] font-mono text-[var(--text-muted)] opacity-60">CTRL+K</span>
          </Link>
        </div>

        {/* Section 2: Data Environment */}
        <div className="space-y-1">
          <span className="label-caps text-[9px] text-[var(--text-muted)] px-3 block mb-1.5 font-bold">Data Environment</span>
          <Link
            href="/connectors"
            className={`flex items-center justify-between rounded-lg px-3 py-2 transition-all duration-250 ease-[cubic-bezier(0.16,1,0.3,1)] ${
              pathname === "/connectors"
                ? "bg-[var(--bg-surface-hover)] text-[var(--text-primary)] border border-[var(--border-focus)] shadow-[var(--shadow-glow)] pl-[12px]"
                : "text-[var(--text-secondary)] hover:bg-[var(--bg-surface)]/40 hover:text-[var(--text-primary)] hover:translate-x-0.5"
            }`}
          >
            <div className="flex items-center gap-2.5">
              <Link2 className="h-3.5 w-3.5 text-[var(--accent)]" />
              <span className="uppercase tracking-wider font-semibold">Connectors</span>
            </div>
            {conversations.length > 0 && (
              <span className="text-[8px] font-mono font-bold bg-[var(--bg-surface)] px-1.5 py-0.5 rounded-md border border-[var(--border-subtle)] text-[var(--text-secondary)]">
                {conversations.length}
              </span>
            )}
          </Link>
        </div>

        {/* Section 3: System Controls (Admin-only) */}
        {isAdmin && (
          <div className="space-y-1">
            <span className="label-caps text-[9px] text-[var(--text-muted)] px-3 block mb-1.5 font-bold">System Monitoring</span>
            <Link
              href="/admin"
              className={`flex items-center gap-2.5 rounded-lg px-3 py-2 transition-all duration-250 ease-[cubic-bezier(0.16,1,0.3,1)] ${
                pathname === "/admin"
                  ? "bg-[var(--bg-surface-hover)] text-[var(--text-primary)] border border-[var(--border-focus)] shadow-[var(--shadow-glow)] pl-[12px]"
                  : "text-[var(--text-secondary)] hover:bg-[var(--bg-surface)]/40 hover:text-[var(--text-primary)] hover:translate-x-0.5"
              }`}
            >
              <BarChart3 className="h-3.5 w-3.5 text-[var(--accent)]" />
              <span className="uppercase tracking-wider font-semibold">Observability</span>
            </Link>
          </div>
        )}

        {/* Section 4: Chat Conversations */}
        <div className="space-y-2 pt-2">
          <div className="flex items-center justify-between px-3 pb-1 border-b border-[var(--border-subtle)]/40 mb-1">
            <span className="label-caps text-[9px] text-[var(--text-muted)] font-bold">Conversations</span>
            <button
              onClick={() => router.push("/")}
              className="p-1 rounded hover:bg-[var(--bg-surface-hover)] text-[var(--text-muted)] hover:text-[var(--text-primary)] transition-all duration-150 active:scale-95"
              title="New Conversation"
            >
              <Plus className="h-3.5 w-3.5 text-[var(--accent)]" />
            </button>
          </div>

          <div className="space-y-1">
            {loading && conversations.length === 0 ? (
              <div className="text-[8px] text-center py-4 text-[var(--text-muted)] uppercase tracking-widest animate-pulse font-mono">
                INITIALIZING...
              </div>
            ) : conversations.length === 0 ? (
              <div className="text-[9px] text-center py-6 text-[var(--text-muted)] leading-relaxed uppercase tracking-wider font-mono">
                NO ACTIVE THREADS
              </div>
            ) : (
              conversations.map((conv) => {
                const isActive = pathname === `/chat/${conv.id}`;
                return (
                  <Link
                    key={conv.id}
                    href={`/chat/${conv.id}`}
                    className={`group flex items-center justify-between rounded-lg px-3 py-2 transition-all duration-200 ease-[cubic-bezier(0.16,1,0.3,1)] ${
                      isActive
                        ? "bg-[var(--bg-surface-hover)] text-[var(--text-primary)] border border-[var(--border-focus)] shadow-sm pl-[12px]"
                        : "text-[var(--text-muted)] hover:bg-[var(--bg-surface)]/30 hover:text-[var(--text-primary)] hover:translate-x-0.5"
                    }`}
                  >
                    <div className="flex items-center gap-2 overflow-hidden pr-2">
                      <MessageSquare className={`h-3.5 w-3.5 shrink-0 ${isActive ? "text-[var(--accent)]" : "text-[var(--text-muted)]"}`} />
                      <span className="truncate text-[12px] font-sans tracking-tight font-medium">{conv.title}</span>
                    </div>
                    <button
                      onClick={(e) => handleDelete(e, conv.id)}
                      className="opacity-0 group-hover:opacity-100 p-0.5 rounded text-[var(--text-muted)] hover:text-[var(--danger)] transition-all duration-150 shrink-0 scale-90 hover:scale-100"
                      title="Delete Thread"
                    >
                      <Trash2 className="h-3 w-3" />
                    </button>
                  </Link>
                );
              })
            )}
          </div>
        </div>
      </div>

      {/* Bottom: Redesigned Profile Card */}
      <div className="mt-auto border-t border-[var(--border-subtle)]/40 p-3">
        <div className="relative profile-menu-container">
          {/* Compact Profile Card */}
          <button 
            onClick={() => setShowProfileMenu(!showProfileMenu)}
            className="flex w-full items-center gap-3 rounded-xl p-2 transition-colors hover:bg-[var(--bg-surface-hover)] group"
          >
            <div className="h-8 w-8 shrink-0 overflow-hidden rounded-lg border border-[var(--border-subtle)] bg-[var(--bg-root)] flex items-center justify-center font-mono text-[10px] font-bold">
              {initials}
            </div>
            <div className="flex flex-col items-start overflow-hidden text-left">
              <span className="truncate text-xs font-semibold text-[var(--text-primary)]">
                {user?.full_name || user?.email?.split("@")[0] || "User"}
              </span>
              <span className="truncate text-[10px] text-[var(--text-muted)] group-hover:text-[var(--text-secondary)] transition-colors">
                {user?.email}
              </span>
            </div>
            <ChevronDown className={`ml-auto h-3.5 w-3.5 text-[var(--text-muted)] transition-transform duration-200 ${showProfileMenu ? "rotate-180" : ""}`} />
          </button>
          
          {/* Dropdown Menu (opens upward) */}
          {showProfileMenu && (
            <div className="absolute bottom-full left-0 right-0 mb-2 rounded-xl border border-[var(--border-subtle)] bg-[var(--bg-surface)] shadow-lg z-50 overflow-hidden animate-fade-in origin-bottom">
              <div className="p-3 border-b border-[var(--border-subtle)]/40 bg-[var(--bg-root)]/50">
                <p className="text-[10px] font-semibold text-[var(--text-primary)] truncate">{user?.full_name || user?.email?.split("@")[0] || "User"}</p>
                <p className="text-[9px] font-mono text-[var(--text-muted)] truncate mt-0.5">{user?.email}</p>
              </div>
              <div className="p-1.5">
                <button
                  onClick={handleSignOut}
                  className="flex w-full items-center gap-2 rounded-lg px-2.5 py-2 text-left text-[10px] font-semibold uppercase tracking-wider text-[var(--danger)] hover:bg-[var(--danger)]/10 transition-colors duration-200"
                >
                  <LogOut className="h-3.5 w-3.5" />
                  Sign Out
                </button>
              </div>
            </div>
          )}
        </div>
      </div>
    </div>
  );
}
