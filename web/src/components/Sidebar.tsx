"use client";

import React, { useState, useEffect, useCallback } from "react";
import Link from "next/link";
import { usePathname, useRouter } from "next/navigation";
import { MessageSquare, Link2, Settings, Shield, Brain, Plus, Trash2, LogOut, ChevronRight } from "lucide-react";
import { apiFetch, getActiveWorkspace, getCurrentUser, signOut } from "@/lib/auth";

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
  const workspaceId = workspace?.id || "default-workspace";
  
  const initials = user?.full_name 
    ? user.full_name.split(" ").map(n => n[0]).join("").toUpperCase().slice(0, 2)
    : user?.email ? user.email.slice(0, 2).toUpperCase() : "US";

  const fetchConversations = useCallback(async () => {
    setLoading(true);
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
  }, [workspaceId]);

  useEffect(() => {
    void fetchConversations();

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

  const handleSignOut = () => {
    signOut();
    router.push("/");
  };

  const navItems = [
    { name: "Chat Engine", href: "/", icon: MessageSquare },
    { name: "Data Sources", href: "/connectors", icon: Link2 },
  ];

  return (
    <div className="flex h-screen w-64 flex-col border-r bg-[#030712]/60 backdrop-blur-2xl text-zinc-300 font-sans select-none relative z-20">
      {/* Brand Header */}
      <div className="flex h-16 items-center gap-3 px-6 border-b border-white/[0.04]">
        <div className="relative flex h-9 w-9 items-center justify-center rounded-xl bg-gradient-to-tr from-primary to-accent shadow-lg shadow-primary/20">
          <Brain className="h-5 w-5 text-black font-extrabold" />
        </div>
        <div className="flex flex-col">
          <span className="text-sm font-black tracking-wider text-white uppercase">Assest</span>
          <span className="text-[10px] font-bold text-primary tracking-widest uppercase">Company Brain</span>
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
              className={`flex items-center justify-between rounded-xl px-3.5 py-2.5 text-xs font-bold uppercase tracking-wider transition-all duration-300 ${
                isActive
                  ? "bg-white text-black shadow-xl shadow-white/5"
                  : "text-zinc-400 hover:bg-white/[0.03] hover:text-white"
              }`}
            >
              <div className="flex items-center gap-3">
                <Icon className="h-4.5 w-4.5" />
                <span>{item.name}</span>
              </div>
              {isActive && <ChevronRight className="h-3 w-3" />}
            </Link>
          );
        })}
      </div>

      <div className="flex items-center justify-between px-6 pt-6 pb-2">
        <span className="text-[10px] font-black uppercase text-zinc-500 tracking-widest">Recent Chats</span>
        <button
          onClick={() => router.push("/")}
          className="p-1.5 rounded-lg hover:bg-white/[0.04] text-zinc-400 hover:text-white transition-all duration-200"
          title="New Conversation"
        >
          <Plus className="h-4 w-4" />
        </button>
      </div>

      {/* Conversations Scroll Container */}
      <div className="flex-1 overflow-y-auto px-3 pb-4 space-y-1 scrollbar-thin">
        {loading && conversations.length === 0 ? (
          <div className="text-[10px] font-bold text-center py-4 text-zinc-500 uppercase tracking-widest animate-pulse">
            Loading...
          </div>
        ) : conversations.length === 0 ? (
          <div className="text-[10px] font-bold text-center py-8 text-zinc-500 uppercase tracking-widest leading-relaxed">
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
                className={`group flex items-center justify-between rounded-xl px-3.5 py-2.5 text-xs font-medium transition-all duration-300 ${
                  isActive
                    ? "bg-white/[0.05] text-white border border-white/[0.08] shadow-lg"
                    : "text-zinc-400 hover:bg-white/[0.02] hover:text-white border border-transparent"
                }`}
              >
                <div className="flex items-center gap-3 overflow-hidden pr-2">
                  <MessageSquare className={`h-4 w-4 shrink-0 ${isActive ? "text-primary" : "text-zinc-500"}`} />
                  <span className="truncate">{conv.title}</span>
                </div>
                <button
                  onClick={(e) => handleDelete(e, conv.id)}
                  className="opacity-0 group-hover:opacity-100 p-1 rounded-md text-zinc-500 hover:text-red-400 hover:bg-white/[0.04] transition-all shrink-0"
                  title="Delete Thread"
                >
                  <Trash2 className="h-3.5 w-3.5" />
                </button>
              </Link>
            );
          })
        )}
      </div>

      {/* Footer Profile Control */}
      <div className="border-t border-white/[0.04] p-4 bg-[#010409]">
        <div className="flex items-center justify-between">
          <div className="flex items-center gap-3 overflow-hidden">
            <div className="h-9 w-9 rounded-xl bg-gradient-to-tr from-blue-500/10 to-indigo-500/10 border border-white/[0.08] flex items-center justify-center text-xs font-black text-primary shrink-0">
              {initials}
            </div>
            <div className="flex flex-col overflow-hidden">
              <span className="text-xs font-bold text-white truncate">
                {user?.full_name || user?.email?.split("@")[0] || "User"}
              </span>
              <span className="text-[10px] text-zinc-500 truncate font-semibold uppercase tracking-tight">
                {workspace?.name || "Workspace"}
              </span>
            </div>
          </div>
          

        </div>
      </div>
    </div>
  );
}
