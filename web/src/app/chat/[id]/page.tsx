"use client";

import { useState, useRef, useEffect, useCallback } from "react";
import { useParams } from "next/navigation";
import { 
  Bot, 
  User, 
  Loader2, 
  Send, 
  Activity, 
  BookOpen, 
  Cpu, 
  ChevronRight, 
  ChevronLeft,
  ShieldCheck,
  Award,
  Workflow
} from "lucide-react";
import { apiFetch, getActiveWorkspace } from "@/lib/auth";
import { CONVERSATIONS_CHANGE_EVENT } from "@/components/Sidebar";
import MarkdownRenderer from "@/components/MarkdownRenderer";
import GroundingIndicator from "@/components/GroundingIndicator";
import SystemSignalsPanel from "@/components/SystemSignalsPanel";
import { parseUTCDate } from "@/lib/date";

interface CitationSource {
  id: number;
  title: string;
  url: string;
  section_heading?: string;
  confidence?: number;
  verified?: boolean;
}

interface Message {
  id: string;
  question: string;
  answer: string;
  sources: { title: string; url: string }[];
  citations?: CitationSource[];
  created_at: string;
  grounding_score?: number;
  tier?: string;
  intent?: string;
  faithfulness_score?: number;
  relevance_score?: number;
  eval_reasoning?: string;
  response_time_ms?: number;
}

interface TracePhase {
  name: string;
  status: "pending" | "running" | "completed" | "failed" | "skipped";
  duration_ms?: number;
  detail?: string;
  description: string;
  metadata?: Record<string, any>;
}

function buildMessageTrace(
  msg: Message | undefined, 
  liveTraceRecord?: Record<string, { start: number; end?: number; status: "pending" | "running" | "completed" | "failed" | "skipped"; detail?: string }>
): TracePhase[] {
  const phases = [
    { key: "routing", name: "Routing", description: "Classifies query intent and routes to the optimal execution tier." },
    { key: "retrieval", name: "Retrieval", description: "Queries vector stores and keyword indexes for relevant context." },
    { key: "verification", name: "Verification", description: "Performs CRAG verification of retrieved document context." },
    { key: "swarm", name: "Swarm Execution", description: "Spawns autonomous agent reasoning loop to decompose and execute complex subtasks." },
    { key: "synthesis", name: "Synthesis", description: "Aggregates and synthesizes outputs from the reasoning agents." },
    { key: "generation", name: "Generation", description: "Generates the final grounded answer with real-time tokens." },
    { key: "evaluation", name: "Evaluation", description: "Performs synchronous faithfulness and relevance checks." },
    { key: "done", name: "Done", description: "Trace execution completed and response committed." }
  ];

  if (!msg) {
    return phases.map(p => ({ ...p, status: "pending" as const }));
  }

  const isStreaming = liveTraceRecord && Object.keys(liveTraceRecord).length > 0;

  return phases.map(p => {
    if (isStreaming) {
      const live = liveTraceRecord[p.key] || { status: "pending" };
      let duration: number | undefined = undefined;
      if (live.start) {
        const endVal = live.end || Date.now();
        duration = endVal - live.start;
      }
      
      let metadata: Record<string, any> | undefined = undefined;
      if (p.key === "routing" && msg.tier) {
        metadata = { tier: msg.tier, intent: msg.intent };
      } else if (p.key === "retrieval" && msg.citations) {
        metadata = { sources_found: msg.citations.length };
      } else if (p.key === "evaluation") {
        metadata = {
          faithfulness: msg.faithfulness_score,
          relevance: msg.relevance_score,
          reasoning: msg.eval_reasoning
        };
      }

      return {
        name: p.name,
        description: p.description,
        status: live.status as any,
        duration_ms: live.status === "pending" || live.status === "skipped" ? undefined : duration,
        detail: live.detail,
        metadata
      };
    } else {
      const tier = msg.tier || "fast_rag";
      const isDirect = tier === "direct";
      const isSwarm = tier === "full_swarm" || tier === "tool_exec";
      const isRag = tier === "fast_rag";

      let status: "pending" | "running" | "completed" | "failed" | "skipped" = "completed";
      let detail = "";
      let metadata: Record<string, any> | undefined = undefined;
      let duration: number | undefined = undefined;

      if (p.key === "retrieval" || p.key === "verification") {
        if (!isRag) {
          status = "skipped";
          detail = `Skipped by ${tier.toUpperCase()} tier routing`;
        } else if (p.key === "retrieval" && msg.citations) {
          metadata = { sources_found: msg.citations.length };
          detail = `${msg.citations.length} sources retrieved.`;
        } else if (p.key === "verification") {
          detail = "CRAG verified context.";
        }
      } else if (p.key === "swarm" || p.key === "synthesis") {
        if (!isSwarm) {
          status = "skipped";
          detail = `Skipped by ${tier.toUpperCase()} tier routing`;
        } else {
          detail = "Agent swarm reasoning execution completed.";
        }
      } else if (p.key === "routing") {
        metadata = { tier, intent: msg.intent || "quick_lookup" };
        detail = `Routed to ${tier} tier.`;
      } else if (p.key === "generation") {
        detail = "Answer generation completed.";
      } else if (p.key === "evaluation") {
        metadata = {
          faithfulness: msg.faithfulness_score,
          relevance: msg.relevance_score,
          reasoning: msg.eval_reasoning
        };
        detail = `Faithfulness: ${msg.faithfulness_score !== undefined ? Math.round(msg.faithfulness_score * 100) + "%" : "N/A"} | Relevance: ${msg.relevance_score !== undefined ? Math.round(msg.relevance_score * 100) + "%" : "N/A"}`;
      } else if (p.key === "done") {
        detail = "Response committed to memory.";
        if (msg.response_time_ms) {
          duration = msg.response_time_ms;
        }
      }

      if (msg.answer && msg.answer.startsWith("Critical:")) {
        if (p.key === "done" || p.key === "evaluation") {
          status = "failed";
          detail = msg.answer;
        }
      }

      return {
        name: p.name,
        description: p.description,
        status,
        duration_ms: duration,
        detail,
        metadata
      };
    }
  });
}

export default function ChatIdPage() {
  const { id } = useParams();
  const [messages, setMessages] = useState<Message[]>([]);
  const [input, setInput] = useState("");
  const [isLoading, setIsLoading] = useState(false);
  const [isConvLoading, setIsConvLoading] = useState(true);
  const [convTitle, setConvTitle] = useState("Conversation");
  const [thinkingLogs, setThinkingLogs] = useState<string[]>([]);
  const [showInspector, setShowInspector] = useState(true);
  const [activeLensTab, setActiveLensTab] = useState<"bi" | "trace" | "signals">("bi");
  const [selectedMessageId, setSelectedMessageId] = useState<string | null>(null);
  const [liveTrace, setLiveTrace] = useState<Record<string, { start: number; end?: number; status: "pending" | "running" | "completed" | "failed" | "skipped"; detail?: string }>>({});
  const [hoveredPhase, setHoveredPhase] = useState<string | null>(null);
  const [streamState, setStreamState] = useState<{ phase: string; detail: string }>({
    phase: "idle",
    detail: "Ready to answer with evals and grounded sources."
  });
  
  const [highlightedCitation, setHighlightedCitation] = useState<number | null>(null);

  const scrollRef = useRef<HTMLDivElement>(null);

  const fetchConversation = useCallback(async () => {
    setIsConvLoading(true);
    try {
      const response = await apiFetch(`/api/conversations/${id}`);
      if (response.ok) {
        const data = await response.json();
        setMessages(data.messages);
        setConvTitle(data.title);
        
        // Auto-select the last assistant message for inspection
        if (data.messages && data.messages.length > 0) {
          const assistantMsgs = data.messages.filter((m: Message) => m.answer);
          if (assistantMsgs.length > 0) {
            setSelectedMessageId(assistantMsgs[assistantMsgs.length - 1].id);
          }
        }
      }
    } catch (error) {
      console.error("Failed to fetch conversation:", error);
    } finally {
      setIsConvLoading(false);
    }
  }, [id]);

  useEffect(() => {
    queueMicrotask(() => void fetchConversation());
  }, [fetchConversation]);

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
    setThinkingLogs(["Connecting to knowledge engine..."]);
    setStreamState({
      phase: "routing",
      detail: "Evaluating route, retrieval depth, and grounding path."
    });
    setHighlightedCitation(null);
    setLiveTrace({
      routing: { start: Date.now(), status: "running", detail: "Evaluating route and intent." },
      retrieval: { start: 0, status: "pending" },
      verification: { start: 0, status: "pending" },
      swarm: { start: 0, status: "pending" },
      synthesis: { start: 0, status: "pending" },
      generation: { start: 0, status: "pending" },
      evaluation: { start: 0, status: "pending" },
      done: { start: 0, status: "pending" }
    });

    const updateLiveTrace = (phaseKey: string, statusText: string) => {
      setLiveTrace((prev) => {
        const next = { ...prev };
        const now = Date.now();

        const completePhase = (k: string) => {
          if (next[k] && next[k].status === "running") {
            next[k] = { ...next[k], status: "completed", end: now };
          }
        };

        const skipPhase = (k: string) => {
          if (next[k] && next[k].status === "pending") {
            next[k] = { ...next[k], status: "skipped" };
          }
        };

        if (phaseKey === "routing") {
          next.routing = { ...next.routing, status: "running", detail: statusText };
        } else if (phaseKey === "retrieval") {
          completePhase("routing");
          skipPhase("swarm");
          skipPhase("synthesis");
          next.retrieval = { start: now, status: "running", detail: statusText };
        } else if (phaseKey === "verification") {
          completePhase("retrieval");
          next.verification = { start: now, status: "running", detail: statusText };
        } else if (phaseKey === "fallback") {
          next.verification = { ...next.verification, status: "running", detail: statusText };
        } else if (phaseKey === "swarm") {
          completePhase("routing");
          skipPhase("retrieval");
          skipPhase("verification");
          next.swarm = { start: now, status: "running", detail: statusText };
        } else if (phaseKey === "synthesis") {
          completePhase("swarm");
          next.synthesis = { start: now, status: "running", detail: statusText };
        } else if (phaseKey === "generation") {
          completePhase("routing");
          completePhase("verification");
          completePhase("synthesis");
          completePhase("swarm");
          skipPhase("retrieval");
          skipPhase("verification");
          skipPhase("swarm");
          skipPhase("synthesis");
          if (next.generation?.status !== "running") {
            next.generation = { start: now, status: "running", detail: statusText };
          } else {
            next.generation = { ...next.generation, detail: statusText };
          }
        } else if (phaseKey === "evaluation") {
          completePhase("generation");
          next.evaluation = { start: now, status: "running", detail: statusText };
        }
        return next;
      });
    };

    const activeWs = getActiveWorkspace();
    if (!activeWs?.id) {
      setStreamState({ phase: "error", detail: "No active workspace is selected." });
      setIsLoading(false);
      setThinkingLogs([]);
      return;
    }
    const workspaceId = activeWs.id;
    // Optimistically add user query to state
    const tempUserMsgId = "user-" + Date.now();
    const tempAssistantMsgId = "assistant-" + Date.now();

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

    setSelectedMessageId(tempAssistantMsgId);

    try {
      const response = await apiFetch("/api/query/stream", {
        method: "POST",
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
      let accumulatedCitations: CitationSource[] = [];
      let responseGrounding = 0;
      let responseTier = "fast_rag";
      let responseIntent = "quick_lookup";
      let responseFaithfulness = 1.0;
      let responseRelevance = 1.0;
      let responseEvalReasoning = "";

      // Append empty assistant container to messages
      setMessages((prev) => [
        ...prev,
        {
          id: tempAssistantMsgId,
          question: queryText,
          answer: "",
          sources: [],
          citations: [],
          created_at: new Date().toISOString()
        }
      ]);

      while (true) {
        const { value, done } = await reader.read();
        if (done) break;

        buffer += decoder.decode(value, { stream: true });
        const lines = buffer.split("\n");
        buffer = lines.pop() || "";

        for (const line of lines) {
          const trimmed = line.trim();
          if (!trimmed.startsWith("data: ")) continue;

          try {
            const rawJson = trimmed.slice(6).trim();
            const data = JSON.parse(rawJson);

            if (data.type === "status") {
              setThinkingLogs((prev) => [...prev, data.status]);
              setStreamState({ phase: data.phase || "thinking", detail: data.status });
              if (data.phase) {
                updateLiveTrace(data.phase, data.status);
              }
              if (data.status.toLowerCase().includes("route:")) {
                const parts = data.status.split("Route:")[1]?.trim() || "";
                const tierMatch = parts.match(/^(\w+)/);
                if (tierMatch) {
                  responseTier = tierMatch[1];
                }
              }
            } else if (data.type === "sources") {
              accumulatedCitations = data.sources || [];
              accumulatedSources = accumulatedCitations.map((c: CitationSource) => ({
                title: c.title,
                url: c.url,
              }));
              setMessages((prev) =>
                prev.map((msg) =>
                  msg.id === tempAssistantMsgId
                    ? { ...msg, sources: accumulatedSources, citations: accumulatedCitations }
                    : msg
                )
              );
              setStreamState({
                phase: "grounding",
                detail: `${accumulatedCitations.length} source${accumulatedCitations.length === 1 ? "" : "s"} fetched.`
              });
              updateLiveTrace("verification", `${accumulatedCitations.length} sources retrieved.`);
            } else if (data.type === "token") {
              accumulatedAnswer += data.token;
              if (accumulatedAnswer.length > 12 && streamState.phase !== "streaming") {
                setStreamState({ phase: "streaming", detail: "Generating answer token by token." });
              }
              setMessages((prev) =>
                prev.map((msg) =>
                  msg.id === tempAssistantMsgId ? { ...msg, answer: accumulatedAnswer } : msg
                )
              );
              updateLiveTrace("generation", "Generating answer token by token.");
            } else if (data.type === "metadata") {
              responseGrounding = data.grounding_score || 0;
              responseTier = data.tier || "fast_rag";
              responseIntent = data.intent || "quick_lookup";
              responseFaithfulness = data.faithfulness_score !== undefined ? data.faithfulness_score : 1.0;
              responseRelevance = data.relevance_score !== undefined ? data.relevance_score : 1.0;
              responseEvalReasoning = data.eval_reasoning || "";

              setMessages((prev) =>
                prev.map((msg) =>
                  msg.id === tempAssistantMsgId
                    ? {
                      ...msg,
                      grounding_score: responseGrounding,
                      tier: responseTier,
                      intent: responseIntent,
                      faithfulness_score: responseFaithfulness,
                      relevance_score: responseRelevance,
                      eval_reasoning: responseEvalReasoning,
                    }
                    : msg
                )
              );
              setStreamState({
                phase: "quality",
                detail: `Faithfulness: ${Math.round(responseFaithfulness * 100)}% | Relevance: ${Math.round(responseRelevance * 100)}%`
              });
              setLiveTrace((prev) => {
                const next = { ...prev };
                const now = Date.now();
                if (next.generation && next.generation.status === "running") {
                  next.generation = { ...next.generation, status: "completed", end: now };
                }
                next.evaluation = {
                  start: now,
                  end: now,
                  status: "completed",
                  detail: `Faithfulness: ${Math.round(responseFaithfulness * 100)}% | Relevance: ${Math.round(responseRelevance * 100)}%`
                };
                return next;
              });
            } else if (data.type === "error") {
              const errorMessage = data.message || data.error || "The model stream reported an error.";
              setThinkingLogs((prev) => [...prev, `Error: ${errorMessage}`]);
              setStreamState({ phase: "error", detail: errorMessage });
              setLiveTrace((prev) => {
                const next = { ...prev };
                const now = Date.now();
                Object.keys(next).forEach((k) => {
                  if (next[k] && next[k].status === "running") {
                    next[k] = { ...next[k], status: "failed", end: now, detail: errorMessage };
                  } else if (next[k] && next[k].status === "pending") {
                    next[k] = { ...next[k], status: "skipped" };
                  }
                });
                return next;
              });
            } else if (data.type === "done") {
              setLiveTrace((prev) => {
                const next = { ...prev };
                const now = Date.now();
                if (next.evaluation && next.evaluation.status === "running") {
                  next.evaluation = { ...next.evaluation, status: "completed", end: now };
                }
                next.done = { start: now, end: now, status: "completed", detail: "Response committed to memory." };
                return next;
              });
              break;
            }
          } catch (err) {
            console.error("SSE parse error", err);
          }
        }
      }

      // Fallback in case of empty answer
      if (!accumulatedAnswer.trim()) {
        const fallback = thinkingLogs.length ? thinkingLogs[thinkingLogs.length - 1] : "No response from assistant.";
        setMessages((prev) =>
          prev.map((msg) => (msg.id === tempAssistantMsgId ? { ...msg, answer: fallback } : msg))
        );
        setStreamState({ phase: "fallback", detail: fallback });
      }

      // Update sidebar conversations
      if (typeof window !== "undefined") {
        window.dispatchEvent(new Event(CONVERSATIONS_CHANGE_EVENT));
      }
    } catch (error) {
      console.error("Failed executing query stream:", error);
      const errMsg = error instanceof Error ? error.message : "Critical: Connection lost to LLM gateway.";
      setMessages((prev) =>
        prev.map((msg) =>
          msg.id === tempAssistantMsgId
            ? { ...msg, answer: "Critical: Connection lost to LLM gateway." }
            : msg
        )
      );
      setLiveTrace((prev) => {
        const next = { ...prev };
        const now = Date.now();
        Object.keys(next).forEach((k) => {
          if (next[k] && next[k].status === "running") {
            next[k] = { ...next[k], status: "failed", end: now, detail: errMsg };
          } else if (next[k] && next[k].status === "pending") {
            next[k] = { ...next[k], status: "skipped" };
          }
        });
        return next;
      });
    } finally {
      setIsLoading(false);
      setThinkingLogs([]);
      setStreamState((prev) =>
        prev.phase === "error"
          ? prev
          : { phase: "idle", detail: "Ready to answer with evals and grounded sources." }
      );
    }
  };

  // Handle pending queries passed from the landing page.
  useEffect(() => {
    if (isConvLoading) return;
    const pendingQuery = sessionStorage.getItem("assest_pending_query");
    if (pendingQuery) {
      sessionStorage.removeItem("assest_pending_query");
      window.setTimeout(() => {
        void handleSend(pendingQuery);
      }, 100);
    }
  // Pending query is a one-shot handoff from the home page; handleSend reads current state at execution time.
  // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [id, isConvLoading]);

  // Find currently active inspected message
  const activeMsg = messages.find(m => m.id === selectedMessageId) || messages[messages.length - 1];

  const getSourcesList = (): CitationSource[] => {
    return activeMsg?.citations || [];
  };

  const handleCitationClick = (citationId: number) => {
    setHighlightedCitation(citationId);
    setActiveLensTab("bi");
    setShowInspector(true);
    setTimeout(() => setHighlightedCitation(null), 3000);
  };

  return (
    <div className="flex h-full bg-background text-foreground relative overflow-hidden font-sans">
      {/* Dynamic Radial glow background */}
      <div className="absolute inset-0 bg-[#060608] z-0 pointer-events-none" />
      <div className="absolute top-0 left-0 w-[500px] h-[500px] bg-primary/2 rounded-full blur-[120px] pointer-events-none" />
      <div className="absolute bottom-0 right-0 w-[500px] h-[500px] bg-secondary/2 rounded-full blur-[120px] pointer-events-none" />

      {/* Center Conversation Pane */}
      <div className="flex-1 flex flex-col min-w-0 border-r border-border h-full relative z-10">
        {/* Thread Header */}
        <header className="border-b border-border px-6 py-3.5 bg-[#0d0d11]/60 backdrop-blur-xl z-20 shrink-0 flex items-center justify-between">
          <div className="flex items-center gap-3">
            <span className="text-[9px] uppercase tracking-widest text-zinc-500 font-black">AI Command Workspace</span>
            <span className="text-zinc-700">/</span>
            <h2 className="text-[11px] font-bold text-white max-w-[280px] md:max-w-[400px] truncate">
              {convTitle}
            </h2>
          </div>
          
          <button
            onClick={() => setShowInspector(!showInspector)}
            className="flex items-center gap-1.5 px-3 py-1.5 rounded-lg border border-border bg-[#111116]/80 text-[9px] font-bold uppercase tracking-wider text-zinc-400 hover:text-white hover:border-[#00f5ff]/30 transition-all cursor-pointer shadow-lg"
          >
            {showInspector ? <ChevronRight className="h-3.5 w-3.5" /> : <ChevronLeft className="h-3.5 w-3.5" />}
            Observability Panel
          </button>
        </header>

        {/* Conversation Stream */}
        <div
          ref={scrollRef}
          className="flex-1 overflow-y-auto p-6 space-y-8 pb-36 scrollbar-thin max-w-3xl w-full mx-auto"
        >
          {messages.map((msg, i) => {
            const isAssistant = !!msg.answer;
            const isInspected = selectedMessageId === msg.id;

            return (
              <div key={msg.id || i} className="space-y-3 animate-fade-in">
                {/* User Card */}
                {msg.question && !isAssistant && (
                  <div className="flex gap-3">
                    <div className="h-6 w-6 rounded-full bg-zinc-900 border border-border flex items-center justify-center shrink-0">
                      <User className="h-3 w-3 text-zinc-400" />
                    </div>
                    <div className="flex-1 space-y-1">
                      <div className="flex items-center gap-2">
                        <span className="text-[9px] font-bold text-white">Client</span>
                        <span className="text-[8px] text-zinc-600">
                          {parseUTCDate(msg.created_at).toLocaleTimeString([], { hour: '2-digit', minute: '2-digit' })}
                        </span>
                      </div>
                      <p className="text-[11px] text-zinc-200 leading-relaxed font-medium mt-0.5">
                        {msg.question}
                      </p>
                    </div>
                  </div>
                )}

                {/* Assistant Card */}
                {isAssistant && (
                  <div 
                    onClick={() => setSelectedMessageId(msg.id)}
                    className={`flex gap-3.5 p-4 rounded-xl border transition-all cursor-pointer relative group ${
                      isInspected 
                        ? "border-[#00f5ff]/20 bg-[#0d0d12]/80 shadow-[0_0_15px_rgba(0,245,255,0.02)]" 
                        : "border-transparent bg-transparent hover:bg-white/[0.01]"
                    }`}
                  >
                    {isInspected && (
                      <div className="absolute top-0 left-0 w-1 h-full bg-[#00f5ff] rounded-l-xl" />
                    )}
                    <div className="h-6 w-6 rounded-full bg-white border border-border flex items-center justify-center shrink-0">
                      <Bot className="h-3 w-3 text-black" />
                    </div>
                    <div className="flex-1 min-w-0 space-y-2">
                      <div className="flex items-center justify-between">
                        <div className="flex items-center gap-2">
                          <span className="text-[9px] font-black text-white uppercase tracking-wider">Assest Assistant</span>
                          <span className="text-[8px] text-zinc-600">
                            {parseUTCDate(msg.created_at).toLocaleTimeString([], { hour: '2-digit', minute: '2-digit' })}
                          </span>
                          {msg.tier && (
                            <span className="text-[7px] font-black text-zinc-400 uppercase bg-[#141419] px-1.5 py-0.5 rounded border border-border tracking-wider">
                              {msg.tier}
                            </span>
                          )}
                        </div>
                        {isInspected && (
                          <span className="text-[8px] font-black text-[#ff00e5] uppercase tracking-widest bg-[#ff00e5]/5 px-2 py-0.5 rounded">
                            Inspecting
                          </span>
                        )}
                      </div>

                      {/* Content Grounding Indicator */}
                      {msg.grounding_score !== undefined && msg.tier && (
                        <GroundingIndicator
                          groundingScore={msg.grounding_score}
                          tier={msg.tier}
                          citationCount={msg.citations?.length || 0}
                        />
                      )}

                      {/* Output content */}
                      <MarkdownRenderer
                        content={msg.answer}
                        citations={msg.citations}
                        onCitationClick={handleCitationClick}
                      />
                    </div>
                  </div>
                )}
              </div>
            );
          })}

          {/* Thinking Stepper */}
          {isLoading && thinkingLogs.length > 0 && (
            <div className="flex gap-3 animate-fade-in p-4 rounded-xl border border-dashed border-border bg-[#0d0d12]/30">
              <div className="h-6 w-6 rounded-full bg-zinc-900 border border-border flex items-center justify-center shrink-0">
                <Cpu className="h-3 w-3 text-[#00f5ff] animate-spin" />
              </div>
              <div className="flex-1 space-y-2">
                <span className="text-[8px] font-black uppercase tracking-widest text-zinc-500">Retrieval Pipeline Status</span>
                <div className="space-y-1.5">
                  {thinkingLogs.slice(-2).map((log, li) => (
                    <div key={li} className="flex items-center gap-2 text-[9px] text-[#00f5ff] font-bold">
                      <span className="w-1.5 h-1.5 rounded-full bg-[#00f5ff] animate-ping" />
                      <span>{log}</span>
                    </div>
                  ))}
                </div>
              </div>
            </div>
          )}
        </div>

        {/* Input Dock */}
        <div className="absolute bottom-0 left-0 right-0 p-6 bg-gradient-to-t from-[#060608] via-[#060608]/95 to-transparent z-15 shrink-0">
          <div className="max-w-3xl mx-auto">
            <div className="relative group">
              <div className="absolute inset-0 bg-[#00f5ff]/[0.01] rounded-2xl blur-lg transition-all" />
              <div className="relative flex items-center gap-2 p-2 rounded-xl border border-border bg-[#0b0b0f] focus-within:border-zinc-800 transition-all shadow-2xl">
                <input
                  type="text"
                  value={input}
                  onChange={(e) => setInput(e.target.value)}
                  onKeyDown={(e) => e.key === "Enter" && handleSend()}
                  placeholder="Ask the brain anything..."
                  className="flex-1 bg-transparent py-3 px-4 text-[11px] text-white placeholder-zinc-500 focus:outline-none"
                  disabled={isLoading}
                />
                <button
                  onClick={() => handleSend()}
                  disabled={!input.trim() || isLoading}
                  className="h-8.5 px-4 rounded-lg bg-white hover:bg-[#00f5ff] hover:text-black text-black text-[9px] font-black tracking-widest uppercase flex items-center justify-center gap-1.5 transition-all shrink-0 cursor-pointer disabled:opacity-30 disabled:hover:bg-white disabled:hover:text-black"
                >
                  {isLoading ? (
                    <Loader2 className="h-3 w-3 animate-spin" />
                  ) : (
                    <>
                      <span>Submit</span>
                      <Send className="h-3 w-3" />
                    </>
                  )}
                </button>
              </div>
            </div>
            <p className="text-center text-[7px] text-zinc-600 uppercase tracking-widest pt-2.5">
              Click any AI message to sync telemetry details.
            </p>
          </div>
        </div>
      </div>

      {/* Right Observability Panel */}
      {showInspector && (
        <div className="w-[420px] border-l border-border bg-[#09090c]/95 backdrop-blur-3xl flex flex-col h-full overflow-y-auto shrink-0 select-none z-10">
          {/* Header */}
          <div className="p-4 border-b border-border flex items-center justify-between shrink-0 bg-[#0f0f13]/60">
            <div className="flex items-center gap-2">
              <Workflow className="h-3.5 w-3.5 text-[#00f5ff]" />
              <span className="text-[9px] font-black uppercase tracking-widest text-white">Observability HUD</span>
            </div>
            <span className="text-[7px] font-black text-zinc-500 uppercase tracking-widest border border-white/[0.05] px-1.5 py-0.5 rounded">
              Backend-backed
            </span>
          </div>

          {/* Sub-Header / Tab Navigation */}
          <div className="grid grid-cols-3 border-b border-border bg-[#060608] text-center">
            <button
              onClick={() => setActiveLensTab("bi")}
              className={`py-2.5 text-[8px] font-black uppercase tracking-widest transition-all cursor-pointer ${
                activeLensTab === "bi" 
                  ? "text-[#00f5ff] border-b-2 border-[#00f5ff]" 
                  : "text-zinc-500 hover:text-zinc-300"
              }`}
            >
              Quality
            </button>
            <button
              onClick={() => setActiveLensTab("trace")}
              className={`py-2.5 text-[8px] font-black uppercase tracking-widest transition-all cursor-pointer ${
                activeLensTab === "trace" 
                  ? "text-[#00f5ff] border-b-2 border-[#00f5ff]" 
                  : "text-zinc-500 hover:text-zinc-300"
              }`}
            >
              Trace
            </button>
            <button
              onClick={() => setActiveLensTab("signals")}
              className={`py-2.5 text-[8px] font-black uppercase tracking-widest transition-all cursor-pointer ${
                activeLensTab === "signals" 
                  ? "text-[#00f5ff] border-b-2 border-[#00f5ff]" 
                  : "text-zinc-500 hover:text-zinc-300"
              }`}
            >
              Signals
            </button>
          </div>

          <div className="p-4 flex-1 space-y-5 overflow-y-auto scrollbar-thin">
            {activeLensTab === "bi" ? (
              // Quality Indicators
              <div className="space-y-4">
                {/* SVG Quality Meters */}
                <div className="space-y-2">
                  <span className="text-[8px] font-black uppercase text-zinc-500 tracking-widest block">LLM-graded metrics</span>
                  
                  <div className="grid grid-cols-3 gap-2">
                    {/* Faithfulness */}
                    <div className="rounded-xl border border-white/[0.04] bg-[#0c0c0e] p-2 flex flex-col items-center justify-center relative overflow-hidden group">
                      <div className="relative w-16 h-16 flex items-center justify-center mt-1">
                        <svg className="w-full h-full transform -rotate-90">
                          <circle cx="32" cy="32" r="26" className="stroke-zinc-900 fill-transparent" strokeWidth="3.5" />
                          <circle 
                            cx="32" 
                            cy="32" 
                            r="26" 
                            className="stroke-emerald-400 fill-transparent transition-all duration-1000 ease-out" 
                            strokeWidth="3.5" 
                            strokeDasharray={2 * Math.PI * 26} 
                            strokeDashoffset={2 * Math.PI * 26 - ((activeMsg?.faithfulness_score !== undefined ? activeMsg.faithfulness_score : 0) * 2 * Math.PI * 26)} 
                            strokeLinecap="round"
                          />
                        </svg>
                        <div className="absolute flex flex-col items-center justify-center">
                          <ShieldCheck className="h-3.5 w-3.5 text-emerald-400" />
                          <span className="text-[10px] font-black text-white mt-0.5">
                            {activeMsg?.faithfulness_score !== undefined ? `${Math.round(activeMsg.faithfulness_score * 100)}%` : "N/A"}
                          </span>
                        </div>
                      </div>
                      <span className="text-[7px] font-black uppercase tracking-widest text-zinc-500 mt-2">Faithfulness</span>
                    </div>

                    {/* Relevance */}
                    <div className="rounded-xl border border-white/[0.04] bg-[#0c0c0e] p-2 flex flex-col items-center justify-center relative overflow-hidden group">
                      <div className="relative w-16 h-16 flex items-center justify-center mt-1">
                        <svg className="w-full h-full transform -rotate-90">
                          <circle cx="32" cy="32" r="26" className="stroke-zinc-900 fill-transparent" strokeWidth="3.5" />
                          <circle 
                            cx="32" 
                            cy="32" 
                            r="26" 
                            className="stroke-indigo-400 fill-transparent transition-all duration-1000 ease-out" 
                            strokeWidth="3.5" 
                            strokeDasharray={2 * Math.PI * 26} 
                            strokeDashoffset={2 * Math.PI * 26 - ((activeMsg?.relevance_score !== undefined ? activeMsg.relevance_score : 0) * 2 * Math.PI * 26)} 
                            strokeLinecap="round"
                          />
                        </svg>
                        <div className="absolute flex flex-col items-center justify-center">
                          <Award className="h-3.5 w-3.5 text-indigo-400" />
                          <span className="text-[10px] font-black text-white mt-0.5">
                            {activeMsg?.relevance_score !== undefined ? `${Math.round(activeMsg.relevance_score * 100)}%` : "N/A"}
                          </span>
                        </div>
                      </div>
                      <span className="text-[7px] font-black uppercase tracking-widest text-zinc-500 mt-2">Relevance</span>
                    </div>

                    {/* Grounding */}
                    <div className="rounded-xl border border-white/[0.04] bg-[#0c0c0e] p-2 flex flex-col items-center justify-center relative overflow-hidden group">
                      <div className="relative w-16 h-16 flex items-center justify-center mt-1">
                        <svg className="w-full h-full transform -rotate-90">
                          <circle cx="32" cy="32" r="26" className="stroke-zinc-900 fill-transparent" strokeWidth="3.5" />
                          <circle 
                            cx="32" 
                            cy="32" 
                            r="26" 
                            className="stroke-[#00f5ff] fill-transparent transition-all duration-1000 ease-out" 
                            strokeWidth="3.5" 
                            strokeDasharray={2 * Math.PI * 26} 
                            strokeDashoffset={2 * Math.PI * 26 - ((activeMsg?.grounding_score !== undefined ? activeMsg.grounding_score : 0) * 2 * Math.PI * 26)} 
                            strokeLinecap="round"
                          />
                        </svg>
                        <div className="absolute flex flex-col items-center justify-center">
                          <Activity className="h-3.5 w-3.5 text-[#00f5ff]" />
                          <span className="text-[10px] font-black text-white mt-0.5">
                            {activeMsg?.grounding_score !== undefined ? `${Math.round(activeMsg.grounding_score * 100)}%` : "N/A"}
                          </span>
                        </div>
                      </div>
                      <span className="text-[7px] font-black uppercase tracking-widest text-zinc-500 mt-2">Grounding</span>
                    </div>
                  </div>
                </div>

                {/* Scorer Reasoning */}
                {activeMsg?.eval_reasoning && (
                  <div className="space-y-1.5">
                    <span className="text-[8px] font-black uppercase text-zinc-500 tracking-widest block">Evaluator Rationale</span>
                    <div className="rounded-xl border border-white/[0.04] bg-[#0c0c0e] p-3 text-[9px] leading-relaxed text-zinc-400 space-y-2.5 font-medium">
                      {activeMsg.eval_reasoning.split("\n\n").map((part, pi) => {
                        const isFaith = part.startsWith("Faithfulness:");
                        const text = part.replace(/^(Faithfulness:|Relevance:)/, "").trim();
                        return (
                          <div key={pi} className="space-y-0.5">
                            <span className="text-[7px] font-black text-white uppercase tracking-widest block">
                              {isFaith ? "Faithfulness verdict" : "Relevance verdict"}
                            </span>
                            <p>{text}</p>
                          </div>
                        );
                      })}
                    </div>
                  </div>
                )}

                {/* Grounding Source Graph */}
                <div className="rounded-xl border border-white/[0.04] bg-[#0c0c0e] p-3.5 space-y-3 relative overflow-hidden">
                  <div className="flex items-center justify-between">
                    <span className="text-[8px] font-black uppercase text-zinc-500 tracking-widest">Grounding Map</span>
                    <span className="text-[8px] font-black text-zinc-500 uppercase">{getSourcesList().length} connections</span>
                  </div>
                  <div className="relative w-full h-[180px] border border-white/[0.02] bg-[#060608] rounded-lg">
                    <svg className="w-full h-full" viewBox="0 0 300 180">
                      {getSourcesList().map((src, idx) => {
                        const angle = (idx / getSourcesList().length) * 2 * Math.PI;
                        const targetX = 150 + Math.cos(angle) * 70;
                        const targetY = 90 + Math.sin(angle) * 55;
                        return (
                          <g key={idx}>
                            <line
                              x1="150"
                              y1="90"
                              x2={targetX}
                              y2={targetY}
                              className="stroke-[#00f5ff]/20 stroke-[1] animate-draw-path"
                              strokeDasharray="3 2"
                            />
                            <circle
                              cx={targetX}
                              cy={targetY}
                              r="6"
                              className="fill-[#ff00e5]/20 stroke-[#ff00e5] stroke-[1] cursor-pointer"
                            />
                            <text
                              x={targetX}
                              y={targetY - 9}
                              textAnchor="middle"
                              className="fill-zinc-500 text-[6px] font-black"
                            >
                              Doc {src.id}
                            </text>
                          </g>
                        );
                      })}
                      
                      {/* Central Query Node */}
                      <circle
                        cx="150"
                        cy="90"
                        r="12"
                        className="fill-[#00f5ff]/20 stroke-[#00f5ff] stroke-[1.5] animate-cyber-pulse"
                      />
                      <text x="150" y="93" textAnchor="middle" className="fill-white text-[7px] font-black uppercase tracking-wider">Query</text>
                    </svg>
                  </div>
                </div>

                {/* Grounded Source List */}
                <div className="space-y-2">
                  <span className="text-[8px] font-black uppercase text-zinc-500 tracking-widest block">Retrieved Vector Chunks</span>
                  <div className="space-y-1.5">
                    {getSourcesList().length === 0 ? (
                      <div className="text-[9px] font-black text-zinc-600 uppercase text-center py-6 border border-dashed border-border rounded-xl">
                        No sources loaded
                      </div>
                    ) : (
                      getSourcesList().map((src, idx) => {
                        const isHighlighted = highlightedCitation === src.id;
                        const confidence = src.confidence !== undefined ? Math.round(src.confidence * 100) : null;
                        return (
                          <div
                            key={idx}
                            className={`flex flex-col p-2.5 rounded-lg border transition-all ${
                              isHighlighted
                                ? "border-[#00f5ff] bg-[#00f5ff]/5 ring-1 ring-[#00f5ff]/20"
                                : "border-border bg-[#0c0c0e] hover:border-zinc-800"
                            }`}
                          >
                            <div className="flex items-center justify-between mb-1.5">
                              <div className="flex items-center gap-1.5 overflow-hidden">
                                <span className="flex items-center justify-center w-3.5 h-3.5 rounded bg-zinc-900 border border-border text-white text-[8px] font-black shrink-0">
                                  {src.id}
                                </span>
                                <BookOpen className="h-3 w-3 text-zinc-500 shrink-0" />
                                <span className="text-[9px] font-bold text-white truncate">{src.title}</span>
                              </div>
                              {confidence !== null && (
                                <span className="text-[7px] font-black text-[#00f5ff] bg-[#00f5ff]/5 px-1.5 py-0.5 rounded border border-[#00f5ff]/10">
                                  {confidence}% similarity
                                </span>
                              )}
                            </div>
                            {src.section_heading && (
                              <span className="text-[7px] text-zinc-500 truncate block mb-1">
                                Section: {src.section_heading}
                              </span>
                            )}
                          </div>
                        );
                      })
                    )}
                  </div>
                </div>
              </div>
            ) : activeLensTab === "trace" ? (
              <div className="space-y-4 animate-fade-in">
                <div className="flex items-center justify-between">
                  <span className="text-[8px] font-black uppercase text-zinc-500 tracking-widest block">Execution path telemetry</span>
                  {activeMsg?.response_time_ms && (
                    <span className="text-[9px] font-black text-[#00f5ff] bg-[#00f5ff]/5 px-2 py-0.5 rounded border border-[#00f5ff]/20">
                      LATENCY: {activeMsg.response_time_ms} ms
                    </span>
                  )}
                </div>

                <div className="rounded-xl border border-white/[0.04] bg-[#0c0c0e] p-4 relative overflow-hidden space-y-4">
                  <div className="relative pl-6 space-y-6">
                    <div className="absolute left-[11px] top-2 bottom-2 w-[1.5px] bg-zinc-900 -z-0" />
                    
                    {buildMessageTrace(activeMsg, activeMsg?.id?.startsWith("assistant-") ? liveTrace : undefined).map((phase, idx) => {
                      const isHovered = hoveredPhase === phase.name;
                      
                      let ringColor = "border-zinc-800 bg-zinc-950 text-zinc-600";
                      let statusText = "Pending";
                      let statusBadgeColor = "text-zinc-500 bg-zinc-900/30 border-zinc-800";
                      
                      if (phase.status === "completed") {
                        ringColor = "border-emerald-500/30 bg-[#0d2118] text-emerald-400";
                        statusText = "Completed";
                        statusBadgeColor = "text-emerald-400 bg-emerald-500/5 border-emerald-500/20";
                      } else if (phase.status === "running") {
                        ringColor = "border-[#00f5ff]/50 bg-[#0d242a] text-[#00f5ff] animate-pulse shadow-[0_0_10px_rgba(0,245,255,0.2)]";
                        statusText = "Running";
                        statusBadgeColor = "text-[#00f5ff] bg-[#00f5ff]/5 border-[#00f5ff]/20";
                      } else if (phase.status === "failed") {
                        ringColor = "border-rose-500/40 bg-[#251216] text-rose-400 shadow-[0_0_10px_rgba(244,63,94,0.15)]";
                        statusText = "Failed";
                        statusBadgeColor = "text-rose-400 bg-rose-500/5 border-rose-500/20";
                      } else if (phase.status === "skipped") {
                        ringColor = "border-zinc-900 bg-zinc-950/40 text-zinc-700 opacity-60";
                        statusText = "Skipped";
                        statusBadgeColor = "text-zinc-600 bg-zinc-950/50 border-zinc-950";
                      }

                      return (
                        <div 
                          key={idx} 
                          className="relative flex items-start gap-4 cursor-pointer group"
                          onMouseEnter={() => setHoveredPhase(phase.name)}
                          onMouseLeave={() => setHoveredPhase(null)}
                        >
                          <div className={`relative z-10 w-6 h-6 rounded-full border flex items-center justify-center text-[10px] font-black transition-all ${ringColor}`}>
                            {phase.status === "completed" ? (
                              <span>✓</span>
                            ) : phase.status === "failed" ? (
                              <span>✗</span>
                            ) : phase.status === "skipped" ? (
                              <span className="text-[7px] font-black uppercase text-zinc-700 scale-[0.8]">skip</span>
                            ) : (
                              <span>{idx + 1}</span>
                            )}
                          </div>

                          <div className="flex-1 space-y-1">
                            <div className="flex items-center justify-between">
                              <h4 className={`text-[10px] font-black uppercase tracking-wider ${phase.status === "running" ? "text-[#00f5ff]" : "text-white"}`}>
                                {phase.name}
                              </h4>
                              <div className="flex items-center gap-1.5">
                                {phase.duration_ms !== undefined && (
                                  <span className="text-[8px] font-black text-zinc-500 font-mono">{phase.duration_ms}ms</span>
                                )}
                                <span className={`text-[7px] font-black uppercase tracking-widest px-1.5 py-0.5 rounded border ${statusBadgeColor}`}>
                                  {statusText}
                                </span>
                              </div>
                            </div>
                            
                            <p className="text-[9px] text-zinc-500 leading-normal font-medium">
                              {phase.detail || phase.description}
                            </p>

                            {isHovered && (
                              <div className="mt-2 p-2.5 rounded-lg border border-[#00f5ff]/20 bg-[#070709] text-[9px] font-medium text-zinc-400 space-y-2 leading-relaxed animate-fade-in z-20 relative">
                                <div className="flex items-center justify-between border-b border-white/[0.03] pb-1.5">
                                  <span className="text-[7px] font-black uppercase tracking-widest text-[#00f5ff]">Telemetry Node Inspection</span>
                                  {phase.duration_ms !== undefined && (
                                    <span className="text-[8px] font-black text-white">{phase.duration_ms} ms elapsed</span>
                                  )}
                                </div>
                                <p className="text-zinc-300 font-semibold">{phase.description}</p>
                                {phase.detail && (
                                  <div className="bg-zinc-950 p-1.5 rounded border border-white/[0.02] text-[8px] font-mono text-zinc-500 whitespace-pre-wrap break-all">
                                    {phase.detail}
                                  </div>
                                )}
                                
                                {phase.metadata && (
                                  <div className="space-y-1.5 pt-1.5 border-t border-white/[0.03]">
                                    {phase.name === "Routing" && (
                                      <div className="grid grid-cols-2 gap-1.5">
                                        <div>
                                          <span className="text-[7px] text-zinc-600 uppercase block font-black">Execution Tier</span>
                                          <span className="text-[8px] text-white uppercase font-bold">{phase.metadata.tier}</span>
                                        </div>
                                        <div>
                                          <span className="text-[7px] text-zinc-600 uppercase block font-black">Intent Type</span>
                                          <span className="text-[8px] text-white uppercase font-bold">{phase.metadata.intent}</span>
                                        </div>
                                      </div>
                                    )}
                                    {phase.name === "Retrieval" && (
                                      <div>
                                        <span className="text-[7px] text-zinc-600 uppercase block font-black">Knowledge Grounding</span>
                                        <span className="text-[8px] text-white font-bold">{phase.metadata.sources_found} sources retrieved</span>
                                      </div>
                                    )}
                                    {phase.name === "Evaluation" && (
                                      <div className="space-y-1.5">
                                        <div className="grid grid-cols-2 gap-2">
                                          <div>
                                            <span className="text-[7px] text-zinc-600 uppercase block font-black">Faithfulness</span>
                                            <span className="text-[8px] text-emerald-400 font-black">
                                              {phase.metadata.faithfulness !== undefined ? `${Math.round(phase.metadata.faithfulness * 100)}%` : "N/A"}
                                            </span>
                                          </div>
                                          <div>
                                            <span className="text-[7px] text-zinc-600 uppercase block font-black">Relevance</span>
                                            <span className="text-[8px] text-indigo-400 font-black">
                                              {phase.metadata.relevance !== undefined ? `${Math.round(phase.metadata.relevance * 100)}%` : "N/A"}
                                            </span>
                                          </div>
                                        </div>
                                        {phase.metadata.reasoning && (
                                          <div>
                                            <span className="text-[7px] text-zinc-600 uppercase block font-black">Evaluator Verdict</span>
                                            <span className="text-[8px] text-zinc-500 leading-normal block italic">"{phase.metadata.reasoning.split("\n\n")[0]?.replace(/^(Faithfulness:|Relevance:)/, "")?.trim() || ""}"</span>
                                          </div>
                                        )}
                                      </div>
                                    )}
                                  </div>
                                )}
                              </div>
                            )}
                          </div>
                        </div>
                      );
                    })}
                  </div>
                </div>
              </div>
            ) : (
              <div className="space-y-4">
                <SystemSignalsPanel />
              </div>
            )}
          </div>
        </div>
      )}
    </div>
  );
}
