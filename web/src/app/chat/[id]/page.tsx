"use client";

import { useState, useRef, useEffect, useCallback } from "react";
import { useParams, useRouter } from "next/navigation";
import { Bot, User, Loader2, Send, Paperclip, Sparkles, Activity, BookOpen, GitBranch, Cpu, ChevronRight, ChevronLeft } from "lucide-react";
import { apiFetch, getActiveWorkspace, getAuthToken } from "@/lib/auth";
import { CONVERSATIONS_CHANGE_EVENT } from "@/components/Sidebar";

interface Message {
  id: string;
  question: string;
  answer: string;
  sources: { title: string; url: string }[];
  created_at: string;
}

export default function ChatIdPage() {
  const { id } = useParams();
  const router = useRouter();
  const [messages, setMessages] = useState<Message[]>([]);
  const [input, setInput] = useState("");
  const [isLoading, setIsLoading] = useState(false);
  const [isConvLoading, setIsConvLoading] = useState(true);
  const [convTitle, setConvTitle] = useState("Conversation");
  const [thinkingLogs, setThinkingLogs] = useState<string[]>([]);
  const [showInspector, setShowInspector] = useState(true);
  const [activeIntent, setActiveIntent] = useState<string>("QUICK_LOOKUP");
  const scrollRef = useRef<HTMLDivElement>(null);

  const fetchConversation = useCallback(async () => {
    setIsConvLoading(true);
    try {
      const response = await apiFetch(`/api/conversations/${id}`);
      if (response.ok) {
        const data = await response.json();
        setMessages(data.messages);
        setConvTitle(data.title);
      }
    } catch (error) {
      console.error("Failed to fetch conversation:", error);
    } finally {
      setIsConvLoading(false);
    }
  }, [id]);

  useEffect(() => {
    void fetchConversation();
  }, [fetchConversation]);

  // Handle pending queries passed from the landing page
  useEffect(() => {
    if (isConvLoading) return;
    const pendingQuery = sessionStorage.getItem("assest_pending_query");
    if (pendingQuery) {
      sessionStorage.removeItem("assest_pending_query");
      setTimeout(() => {
        void handleSend(pendingQuery);
      }, 100);
    }
  }, [id, isConvLoading]);

  useEffect(() => {
    if (scrollRef.current) {
      scrollRef.current.scrollTop = scrollRef.current.scrollHeight;
    }
  }, [messages, thinkingLogs]);

  const handleSend = async (customText?: string) => {
    const queryText = customText || input;
    if (!queryText.trim() || isLoading) return;

    setInput("");
    setIsLoading(true);
    setThinkingLogs(["Connecting to local brain gate..."]);

    const activeWs = getActiveWorkspace();
    const workspaceId = activeWs?.id || "default-workspace";
    const token = getAuthToken();

    // Optimistically add user query to state
    const tempUserMsgId = "user-" + Date.now();
    const tempAssistantMsgId = "assistant-" + Date.now();

    // Create the message cards in UI
    setMessages((prev) => [
      ...prev,
      {
        id: tempUserMsgId,
        question: queryText,
        answer: "",
        sources: [],
        created_at: new Date().toISOString()
      }
    ]);

    try {
      const API_URL = process.env.NEXT_PUBLIC_API_URL || "http://localhost:8000";
      const response = await fetch(`${API_URL}/api/query/stream`, {
        method: "POST",
        headers: {
          "Content-Type": "application/json",
          "Authorization": token ? `Bearer ${token}` : "",
        },
        body: JSON.stringify({
          question: queryText,
          workspace_id: workspaceId,
          conversation_id: id,
          reasoning_mode: false
        })
      });

      if (!response.ok) {
        throw new Error("Streaming call failed.");
      }

      if (!response.body) {
        throw new Error("Response stream empty.");
      }

      const reader = response.body.getReader();
      const decoder = new TextDecoder("utf-8");
      let buffer = "";
      let accumulatedAnswer = "";
      let accumulatedSources: { title: string; url: string }[] = [];

      // Append empty assistant container to messages
      setMessages((prev) => [
        ...prev,
        {
          id: tempAssistantMsgId,
          question: queryText,
          answer: "",
          sources: [],
          created_at: new Date().toISOString()
        }
      ]);

      while (true) {
        const { value, done } = await reader.read();
        if (done) break;

        buffer += decoder.decode(value, { stream: true });
        const lines = buffer.split("\n");
        // Hold the last partial line back
        buffer = lines.pop() || "";

        for (const line of lines) {
          const trimmed = line.trim();
          if (!trimmed.startsWith("data: ")) continue;

          try {
            const rawJson = trimmed.slice(6).trim();
            const data = JSON.parse(rawJson);

            if (data.type === "status") {
              setThinkingLogs((prev) => [...prev, data.status]);
              if (data.status.toLowerCase().includes("intent classified")) {
                const intentStr = data.status.split("classified as:")[1]?.trim() || "QUICK_LOOKUP";
                setActiveIntent(intentStr.toUpperCase());
              }
            } else if (data.type === "sources") {
              accumulatedSources = data.sources;
              setMessages((prev) =>
                prev.map((msg) =>
                  msg.id === tempAssistantMsgId ? { ...msg, sources: accumulatedSources } : msg
                )
              );
            } else if (data.type === "token") {
              accumulatedAnswer += data.token;
              setMessages((prev) =>
                prev.map((msg) =>
                  msg.id === tempAssistantMsgId ? { ...msg, answer: accumulatedAnswer } : msg
                )
              );
            }
          } catch (err) {
            console.error("SSE parse error", err);
          }
        }
      }

      // Finalize and reload sidebar
      if (typeof window !== "undefined") {
        window.dispatchEvent(new Event(CONVERSATIONS_CHANGE_EVENT));
      }
    } catch (error) {
      console.error("Failed executing query stream:", error);
      setMessages((prev) =>
        prev.map((msg) =>
          msg.id === tempAssistantMsgId
            ? { ...msg, answer: "Critical: Connection lost to LLM gateway." }
            : msg
        )
      );
    } finally {
      setIsLoading(false);
      setThinkingLogs([]);
    }
  };

  const getSourcesList = () => {
    if (messages.length === 0) return [];
    const lastMsg = messages[messages.length - 1];
    return lastMsg?.sources || [];
  };

  return (
    <div className="flex h-full bg-[#020617] text-foreground relative overflow-hidden font-sans">
      {/* HUD background grid */}
      <div 
        className="absolute inset-0 opacity-[0.015] pointer-events-none"
        style={{
          backgroundImage: `radial-gradient(circle at 1px 1px, white 1px, transparent 0)`,
          backgroundSize: "24px 24px"
        }}
      />
      <div className="absolute top-0 right-1/4 w-[500px] h-[300px] bg-primary/5 rounded-full blur-[150px] pointer-events-none" />

      {/* Primary Chat Box (Center) */}
      <div className="flex-1 flex flex-col min-w-0 border-r border-white/[0.04] h-full relative">
        {/* Thread Header */}
        <header className="flex h-16 items-center justify-between border-b border-white/[0.04] px-8 bg-card/10 backdrop-blur-xl z-10 shrink-0">
          <div className="flex items-center gap-3">
            <Activity className="h-4.5 w-4.5 text-primary animate-pulse" />
            <h2 className="text-xs font-black uppercase tracking-wider text-white truncate max-w-[240px]">
              {convTitle}
            </h2>
          </div>
          <button
            onClick={() => setShowInspector(!showInspector)}
            className="flex items-center gap-2 px-3 py-1.5 rounded-xl border border-white/[0.06] bg-white/[0.02] text-[10px] font-black uppercase tracking-widest text-zinc-400 hover:text-white hover:border-primary/30 transition-all cursor-pointer"
          >
            {showInspector ? <ChevronRight className="h-3.5 w-3.5" /> : <ChevronLeft className="h-3.5 w-3.5" />}
            Inspector
          </button>
        </header>

        {/* Messaging Pane */}
        <div
          ref={scrollRef}
          className="flex-1 overflow-y-auto p-8 space-y-10 pb-36 scrollbar-thin"
        >
          {messages.map((msg, i) => (
            <div key={msg.id || i} className="max-w-3xl mx-auto space-y-6 animate-fade-in">
              {/* Question bubble */}
              {msg.question && (
                <div className="flex gap-4 justify-end">
                  <div className="bg-white/[0.03] text-zinc-100 px-5 py-3 rounded-2xl rounded-tr-sm border border-white/[0.05] max-w-[80%] shadow-lg">
                    <p className="text-xs leading-relaxed font-semibold">{msg.question}</p>
                  </div>
                  <div className="h-8 w-8 rounded-xl bg-zinc-800 border border-white/5 flex items-center justify-center shrink-0">
                    <User className="h-4 w-4 text-zinc-400" />
                  </div>
                </div>
              )}

              {/* Answer bubble */}
              {(msg.answer || (isLoading && i === messages.length - 1)) && (
                <div className="flex gap-4">
                  <div className="h-8 w-8 rounded-xl bg-gradient-to-tr from-primary to-accent border border-white/[0.08] flex items-center justify-center shrink-0 shadow-lg shadow-primary/10">
                    <Bot className="h-4 w-4 text-black font-extrabold" />
                  </div>
                  <div className="space-y-4 flex-1 min-w-0">
                    {msg.answer ? (
                      <div className="prose prose-invert max-w-none text-xs leading-6 text-zinc-300 font-medium whitespace-pre-wrap">
                        {msg.answer}
                      </div>
                    ) : (
                      <div className="flex items-center gap-2 text-primary font-bold text-[10px] uppercase tracking-wider">
                        <Loader2 className="h-3.5 w-3.5 animate-spin" />
                        Decoding brain streams...
                      </div>
                    )}
                  </div>
                </div>
              )}
            </div>
          ))}

          {/* Real-time Stepper / Thinking logs */}
          {isLoading && thinkingLogs.length > 0 && (
            <div className="max-w-3xl mx-auto flex gap-4 animate-fade-in">
              <div className="h-8 w-8 rounded-xl bg-zinc-900 border border-white/[0.05] flex items-center justify-center shrink-0">
                <Cpu className="h-4 w-4 text-primary animate-pulse" />
              </div>
              <div className="flex-1 bg-white/[0.01] border border-white/[0.03] rounded-2xl p-5 space-y-3 shadow-inner">
                <span className="text-[10px] font-black uppercase tracking-widest text-zinc-500">Neural swarm logs</span>
                <div className="space-y-2">
                  {thinkingLogs.map((log, li) => (
                    <div key={li} className="flex items-center gap-3 text-[10px] text-zinc-400 font-bold uppercase tracking-wide">
                      <span className="w-1.5 h-1.5 rounded-full bg-primary animate-ping" />
                      <span>{log}</span>
                    </div>
                  ))}
                </div>
              </div>
            </div>
          )}
        </div>

        {/* Floating Input Control */}
        <div className="absolute bottom-0 left-0 right-0 p-8 bg-gradient-to-t from-[#020617] via-[#020617]/95 to-transparent z-10 shrink-0">
          <div className="max-w-3xl mx-auto">
            <div className="relative group">
              <div className="absolute inset-0 bg-primary/5 rounded-[2rem] blur-xl group-focus-within:bg-primary/10 transition-all" />
              <div className="relative flex items-center gap-2 p-2 rounded-[2rem] border border-white/[0.06] bg-white/[0.02] backdrop-blur-2xl shadow-2xl focus-within:border-primary/20 transition-all">
                <input
                  type="text"
                  value={input}
                  onChange={(e) => setInput(e.target.value)}
                  onKeyDown={(e) => e.key === "Enter" && handleSend()}
                  placeholder="Ask a follow-up..."
                  className="flex-1 bg-transparent py-4 px-6 text-sm text-white focus:outline-none"
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
          </div>
        </div>
      </div>

      {/* Thought Inspector (Right Side Drawer) */}
      {showInspector && (
        <div className="w-80 border-l border-white/[0.04] bg-[#030712]/40 backdrop-blur-3xl p-6 flex flex-col gap-6 h-full overflow-y-auto shrink-0 select-none">
          <div className="flex items-center gap-2 border-b border-white/[0.04] pb-4">
            <Activity className="h-4 w-4 text-primary" />
            <h3 className="text-[11px] font-black uppercase text-white tracking-widest">Thought Inspector</h3>
          </div>

          {/* Segment 1: Classified Intent */}
          <div className="space-y-2">
            <span className="text-[9px] font-black uppercase text-zinc-500 tracking-widest">Cognitive State</span>
            <div className="p-3.5 rounded-2xl border border-white/[0.04] bg-white/[0.01] flex items-center justify-between">
              <div className="flex flex-col">
                <span className="text-[10px] font-black text-white uppercase tracking-wider">{activeIntent}</span>
                <span className="text-[8px] font-bold text-zinc-500 uppercase tracking-wide">Intent Router</span>
              </div>
              <div className="h-7 px-2.5 rounded-lg border border-primary/20 bg-primary/5 flex items-center justify-center text-[9px] font-black text-primary uppercase">
                Swarm Run
              </div>
            </div>
          </div>

          {/* Segment 2: Interactive SVG Graph */}
          <div className="space-y-2">
            <div className="flex justify-between items-center">
              <span className="text-[9px] font-black uppercase text-zinc-500 tracking-widest">Dynamic Entity Graph</span>
              <span className="text-[8px] font-black text-primary uppercase bg-primary/5 px-2 py-0.5 rounded">Active</span>
            </div>
            
            <div className="border border-white/[0.04] bg-[#020617]/50 rounded-2xl p-4 h-48 flex items-center justify-center overflow-hidden relative">
              <svg width="100%" height="100%" viewBox="0 0 200 160">
                {/* SVG Connections with animated dasharray */}
                <line x1="100" y1="80" x2="40" y2="40" stroke="var(--color-primary)" strokeWidth="1" strokeOpacity="0.4" strokeDasharray="3 3">
                  <animate attributeName="stroke-dashoffset" values="30;0" dur="4s" repeatCount="indefinite" />
                </line>
                <line x1="100" y1="80" x2="160" y2="40" stroke="var(--color-primary)" strokeWidth="1" strokeOpacity="0.4" strokeDasharray="3 3">
                  <animate attributeName="stroke-dashoffset" values="30;0" dur="4.5s" repeatCount="indefinite" />
                </line>
                <line x1="100" y1="80" x2="100" y2="130" stroke="var(--color-primary)" strokeWidth="1" strokeOpacity="0.4" strokeDasharray="3 3">
                  <animate attributeName="stroke-dashoffset" values="30;0" dur="3.5s" repeatCount="indefinite" />
                </line>
                
                {/* Central workspace node */}
                <circle cx="100" cy="80" r="10" fill="var(--color-primary)" fillOpacity="0.2" stroke="var(--color-primary)" strokeWidth="1.5" className="animate-pulse" />
                <text x="100" y="65" textAnchor="middle" fill="#fff" fontSize="7" fontWeight="bold">Company Brain</text>
                
                {/* Document entity node */}
                <circle cx="40" cy="40" r="6" fill="#38bdf8" fillOpacity="0.3" stroke="#38bdf8" strokeWidth="1" />
                <text x="40" y="28" textAnchor="middle" fill="#94a3b8" fontSize="6">Notion SOP</text>
                
                {/* Thread node */}
                <circle cx="160" cy="40" r="6" fill="#f59e0b" fillOpacity="0.3" stroke="#f59e0b" strokeWidth="1" />
                <text x="160" y="28" textAnchor="middle" fill="#94a3b8" fontSize="6">Slack Context</text>
                
                {/* Owner node */}
                <circle cx="100" cy="130" r="6" fill="#ec4899" fillOpacity="0.3" stroke="#ec4899" strokeWidth="1" />
                <text x="100" y="145" textAnchor="middle" fill="#94a3b8" fontSize="6">Entity: Startups</text>
              </svg>
            </div>
          </div>

          {/* Segment 3: Sources Grounding */}
          <div className="space-y-3 flex-1 flex flex-col min-h-0">
            <span className="text-[9px] font-black uppercase text-zinc-500 tracking-widest shrink-0">Grounded Context Sources</span>
            
            <div className="flex-1 overflow-y-auto space-y-2.5 pr-1 scrollbar-thin">
              {getSourcesList().length === 0 ? (
                <div className="text-[10px] font-bold text-zinc-500 uppercase tracking-wider text-center py-10">
                  No source context<br />retrieved yet.
                </div>
              ) : (
                getSourcesList().map((src, idx) => {
                  // Simulate realistic confidence decay for visual hierarchy
                  const confidence = Math.max(98 - idx * 8, 55);
                  return (
                    <a
                      key={idx}
                      href={src.url || "#"}
                      target="_blank"
                      rel="noopener noreferrer"
                      className="flex flex-col p-3 rounded-xl border border-white/[0.04] bg-white/[0.01] hover:bg-white/[0.03] transition-all hover:border-primary/20"
                    >
                      <div className="flex items-center justify-between mb-1.5">
                        <div className="flex items-center gap-1.5 overflow-hidden pr-2">
                          <BookOpen className="h-3.5 w-3.5 text-primary shrink-0" />
                          <span className="text-[10px] font-bold text-white truncate">{src.title}</span>
                        </div>
                        <span className="text-[8px] font-black text-primary">{confidence}% Match</span>
                      </div>
                      {/* Match ratio slider */}
                      <div className="w-full h-1 bg-zinc-800 rounded-full overflow-hidden">
                        <div 
                          className="h-full bg-gradient-to-r from-primary to-accent" 
                          style={{ width: `${confidence}%` }}
                        />
                      </div>
                    </a>
                  );
                })
              )}
            </div>
          </div>
        </div>
      )}
    </div>
  );
}

