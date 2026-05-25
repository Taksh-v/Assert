"use client";

import { useState } from "react";
import { useRouter } from "next/navigation";
import { Bot, Loader2, Sparkles, Send } from "lucide-react";
import { apiFetch, getActiveWorkspace } from "@/lib/auth";
import { CONVERSATIONS_CHANGE_EVENT } from "@/components/Sidebar";

export default function ChatPage() {
  const [input, setInput] = useState("");
  const [isLoading, setIsLoading] = useState(false);
  const router = useRouter();

  const handleSend = async (customText?: string) => {
    const textToSend = customText || input;
    if (!textToSend.trim() || isLoading) return;

    setIsLoading(true);

    try {
      const activeWs = getActiveWorkspace();
      const workspaceId = activeWs?.id || "default-workspace";

      // 1. Create a new conversation thread on the backend
      const response = await apiFetch("/api/conversations", {
        method: "POST",
        body: JSON.stringify({
          workspace_id: workspaceId,
          title: textToSend.length > 50 ? textToSend.slice(0, 50) + "..." : textToSend,
        })
      });

      if (!response.ok) {
        throw new Error("Failed to create conversation thread.");
      }

      const data = await response.json();
      const convId = data.id;

      // 2. Write the query to session storage so the chat detail page can execute it
      sessionStorage.setItem("assest_pending_query", textToSend);

      // 3. Dispatch conversations update event for sidebar
      if (typeof window !== "undefined") {
        window.dispatchEvent(new Event(CONVERSATIONS_CHANGE_EVENT));
      }

      // 4. Redirect to the newly created conversation page
      router.push(`/chat/${convId}`);
    } catch (error) {
      console.error("Error starting new conversation:", error);
      setIsLoading(false);
    }
  };

  const suggestions = [
    "What is the refund policy?",
    "How do I set up my dev environment?",
    "Who is the lead for Project Phoenix?",
    "Show me the latest marketing assets"
  ];

  return (
    <div className="flex flex-col h-full bg-background relative overflow-hidden font-sans">
      {/* Decorative Glows */}
      <div className="absolute top-0 left-1/4 w-[500px] h-[300px] bg-primary/10 rounded-full blur-[120px] pointer-events-none" />
      <div className="absolute bottom-0 right-1/4 w-[400px] h-[250px] bg-accent/5 rounded-full blur-[100px] pointer-events-none" />

      {/* Header */}
      <header className="flex h-16 items-center justify-between border-b border-white/[0.04] px-8 bg-[#020617]/50 backdrop-blur-xl z-10">
        <div className="flex items-center gap-2">
          <Sparkles className="h-5 w-5 text-primary" />
          <h2 className="text-sm font-black uppercase tracking-wider text-white">Knowledge Hub</h2>
        </div>
        <div className="text-[10px] font-black uppercase tracking-widest text-zinc-500">
          v1.0.0-neural
        </div>
      </header>

      {/* Main Home Hero */}
      <div className="flex-1 flex flex-col items-center justify-center p-8 space-y-12 max-w-4xl mx-auto z-10">
        <div className="flex flex-col items-center text-center space-y-4">
          <div className="relative group">
            <div className="absolute inset-0 bg-primary/20 rounded-3xl blur-2xl group-hover:bg-primary/30 transition-all duration-500" />
            <div className="relative flex h-20 w-20 items-center justify-center rounded-3xl border border-white/[0.08] bg-white/[0.02] backdrop-blur-3xl shadow-2xl">
              <Bot className="h-10 w-10 text-primary" />
            </div>
          </div>
          <div className="space-y-2">
            <h3 className="text-3xl font-black text-white sm:text-4xl tracking-tight leading-none">
              Ask your <span className="bg-gradient-to-r from-primary to-accent bg-clip-text text-transparent">Company Brain</span>
            </h3>
            <p className="text-sm text-zinc-400 max-w-md mx-auto font-medium">
              Seamless semantic search and multi-agent swarm reasoning across Notion, Google Drive, and Slack channels.
            </p>
          </div>
        </div>

        {/* Suggestion Cards */}
        <div className="grid grid-cols-1 md:grid-cols-2 gap-4 w-full max-w-2xl">
          {suggestions.map((q) => (
            <button
              key={q}
              onClick={() => handleSend(q)}
              className="glass-card px-5 py-4 text-xs font-bold text-zinc-300 hover:text-white rounded-2xl text-left border border-white/[0.04] transition-all hover:scale-[1.01] active:scale-[0.99] flex items-center justify-between"
            >
              <span>{q}</span>
              <Sparkles className="h-3.5 w-3.5 text-primary opacity-0 group-hover:opacity-100 transition-opacity" />
            </button>
          ))}
        </div>
      </div>

      {/* Centralized Search Input */}
      <div className="p-8 border-t border-white/[0.04] bg-[#020617]/80 backdrop-blur-3xl z-10">
        <div className="max-w-3xl mx-auto">
          <div className="relative group">
            <div className="absolute inset-0 bg-primary/5 rounded-[2rem] blur-xl group-focus-within:bg-primary/10 transition-all" />
            <div className="relative flex items-center gap-2 p-2 rounded-[2rem] border border-white/[0.06] bg-white/[0.02] backdrop-blur-2xl shadow-2xl focus-within:border-primary/30 transition-all">
              <input
                type="text"
                value={input}
                onChange={(e) => setInput(e.target.value)}
                onKeyDown={(e) => e.key === "Enter" && handleSend()}
                placeholder="Ask Assest anything..."
                className="flex-1 bg-transparent py-4 px-6 text-sm text-white placeholder-zinc-500 focus:outline-none"
                disabled={isLoading}
              />
              <button
                onClick={() => handleSend()}
                disabled={!input.trim() || isLoading}
                className="h-12 w-12 rounded-full bg-white hover:bg-primary hover:scale-105 active:scale-95 disabled:opacity-30 disabled:hover:bg-white disabled:hover:scale-100 shadow-lg text-black font-black flex items-center justify-center transition-all shrink-0 cursor-pointer"
              >
                {isLoading ? (
                  <Loader2 className="h-5 w-5 animate-spin text-black" />
                ) : (
                  <Send className="h-5 w-5" />
                )}
              </button>
            </div>
          </div>
          <p className="text-center text-[9px] text-zinc-500 font-bold uppercase tracking-widest pt-4">
            Secured by enterprise-grade token sanitization & PII scrubbing.
          </p>
        </div>
      </div>
    </div>
  );
}

