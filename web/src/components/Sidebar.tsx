"use client";

import React, { useState, useEffect, useCallback } from "react";
import Link from "next/link";
import { usePathname, useRouter } from "next/navigation";
import { MessageSquare, Link2, Brain, Plus, Trash2, ChevronRight } from "lucide-react";
import { apiFetch, getActiveWorkspace, getCurrentUser } from "@/lib/auth";

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
  
  const user = getCurrentUser();
  const workspace = getActiveWorkspace();
  const workspaceId = workspace?.id;
  
  const initials = user?.full_name 
    ? user.full_name.split(" ").map(n => n[0]).join("").toUpperCase().slice(0, 2)
    : user?.email ? user.email.slice(0, 2).toUpperCase() : "US";

  const fetchConversations = useCallback(async () => {
    setLoading(true);
    try {
      if (!workspaceId) {
        setConversations([]);
        return;
      }
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
  }, [workspaceId]);

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

  const navItems = [
    { name: "Chat Engine", href: "/", icon: MessageSquare },
    { name: "Data Sources", href: "/connectors", icon: Link2 },
  ];

  return (
    <div className="flex h-screen w-64 flex-col border-r border-border bg-[#050505] text-zinc-400 font-sans select-none relative z-20">
      {/* Brand Header */}
      <div className="flex h-16 items-center gap-3 px-6 border-b border-border">
        <div className="relative flex h-8 w-8 items-center justify-center rounded-lg border border-border bg-[#0e0e0e]">
          <Brain className="h-4.5 w-4.5 text-white" />
        </div>
        <div className="flex flex-col">
          <span className="text-xs font-bold tracking-wider text-white uppercase">Assest</span>
          <span className="text-[9px] font-medium text-zinc-500 tracking-wider uppercase">Company Brain</span>
        </div>
      </div>

      {/* Main Navigation */}
      <div className="px-3 pt-4 space-y-1">
        {navItems.map((item) => {
          const Icon = item.icon;
          const isActive = pathname === item.href || (item.href === "/" && pathname.startsWith("/chat"));

          return (
            <Link
              key={item.name}
              href={item.href}
              className={`flex items-center justify-between rounded-lg px-3 py-2 text-[11px] font-bold uppercase tracking-wider transition-all duration-200 border ${
                isActive
                  ? "bg-white/[0.04] text-white border-border shadow-sm"
                  : "text-zinc-400 hover:bg-white/[0.015] hover:text-white border-transparent"
              }`}
            >
              <div className="flex items-center gap-2.5">
                <Icon className="h-4 w-4" />
                <span>{item.name}</span>
              </div>
              {isActive && <ChevronRight className="h-3 w-3 text-zinc-500" />}
            </Link>
          );
        })}
      </div>

      <div className="flex items-center justify-between px-6 pt-6 pb-2">
        <span className="text-[9px] font-bold uppercase text-zinc-500 tracking-wider">Recent Chats</span>
        <button
          onClick={() => router.push("/")}
          className="p-1 rounded-md hover:bg-white/[0.03] text-zinc-500 hover:text-white transition-all"
          title="New Conversation"
        >
          <Plus className="h-3.5 w-3.5" />
        </button>
      </div>

      {/* Conversations Scroll Container */}
      <div className="flex-1 overflow-y-auto px-3 pb-4 space-y-1 scrollbar-thin">
        {loading && conversations.length === 0 ? (
          <div className="text-[9px] font-bold text-center py-4 text-zinc-650 uppercase tracking-widest animate-pulse">
            Loading...
          </div>
        ) : conversations.length === 0 ? (
          <div className="text-[9px] font-bold text-center py-8 text-zinc-600 uppercase tracking-widest leading-relaxed">
            No active threads.<br />
            Start one above.
          </div>
        ) : (
          conversations.map((conv) => {
            const isActive = pathname === `/chat/${conv.id}`;
            return (
              <Link
                key={conv.id}
                href={`/chat/${conv.id}`}
                className={`group flex items-center justify-between rounded-lg px-3 py-2 text-xs font-medium border transition-all ${
                  isActive
                    ? "bg-white/[0.02] text-white border-border shadow-inner"
                    : "text-zinc-500 hover:bg-white/[0.01] hover:text-white border-transparent"
                }`}
              >
                <div className="flex items-center gap-2.5 overflow-hidden pr-2">
                  <MessageSquare className={`h-3.5 w-3.5 shrink-0 ${isActive ? "text-white" : "text-zinc-600"}`} />
                  <span className="truncate">{conv.title}</span>
                </div>
                <button
                  onClick={(e) => handleDelete(e, conv.id)}
                  className="opacity-0 group-hover:opacity-100 p-0.5 rounded text-zinc-600 hover:text-red-400 hover:bg-white/[0.03] transition-all shrink-0"
                  title="Delete Thread"
                >
                  <Trash2 className="h-3 w-3" />
                </button>
              </Link>
            );
          })
        )}
      </div>

      {/* Footer Profile Control */}
      <div className="border-t border-border p-4 bg-[#050505]">
        <div className="flex items-center justify-between">
          <div className="flex items-center gap-3 overflow-hidden">
            <div className="h-8 w-8 rounded-lg bg-zinc-900 border border-border flex items-center justify-center text-[10px] font-bold text-white shrink-0">
              {initials}
            </div>
            <div className="flex flex-col overflow-hidden">
              <span className="text-xs font-bold text-white truncate">
                {user?.full_name || user?.email?.split("@")[0] || "User"}
              </span>
              <span className="text-[9px] text-zinc-600 truncate font-bold uppercase tracking-wide">
                {workspace?.name || "Workspace"}
              </span>
            </div>
          </div>
        </div>
      </div>
    </div>
  );
}
