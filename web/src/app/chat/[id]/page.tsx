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
  ShieldCheck,
  Award,
  Workflow,
  AlertCircle,
  Paperclip,
  UploadCloud,
  FileText,
  CheckCircle2,
  Database
} from "lucide-react";
import { useDropzone } from "react-dropzone";
import { toast } from "sonner";
import { apiFetch, getActiveWorkspace, isAdminWorkspaceRole, AUTH_CHANGE_EVENT } from "@/lib/auth";
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

interface UserProfile {
  tone?: string;
  complexity?: string;
  expertise?: string;
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
  disclaimer?: string;
  user_profile?: UserProfile;
}

interface TracePhase {
  name: string;
  status: "pending" | "running" | "completed" | "failed" | "skipped";
  duration_ms?: number;
  detail?: string;
  description: string;
  metadata?: TraceMetadata;
}

interface TraceMetadata {
  tier?: string;
  intent?: string;
  sources_found?: number;
  faithfulness?: number | null;
  relevance?: number | null;
  reasoning?: string | null;
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
      
      let metadata: TraceMetadata | undefined = undefined;
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
        status: live.status as TracePhase["status"],
        duration_ms: live.status === "pending" || live.status === "skipped" ? undefined : duration,
        detail: live.detail,
        metadata
      };
    } else {
      const tier = msg.tier || "fast_rag";
      const isSwarm = tier === "full_swarm" || tier === "tool_exec";
      const isRag = tier === "fast_rag";

      let status: "pending" | "running" | "completed" | "failed" | "skipped" = "completed";
      let detail = "";
      let metadata: TraceMetadata | undefined = undefined;
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
  const [isUploading, setIsUploading] = useState(false);
  const [uploadingFileName, setUploadingFileName] = useState("");
  const [uploadStatus, setUploadStatus] = useState<{ success: boolean; message: string } | null>(null);
  const [isConvLoading, setIsConvLoading] = useState(true);
  const [convTitle, setConvTitle] = useState("Conversation");
  const [thinkingLogs, setThinkingLogs] = useState<string[]>([]);
  const [activeWorkspace, setActiveWorkspace] = useState(getActiveWorkspace());
  const isAdmin = isAdminWorkspaceRole(activeWorkspace?.role);
  
  const [uploadedSessionFiles, setUploadedSessionFiles] = useState<{name: string, status: 'processing' | 'ready'}[]>([]);
  const [workspaceDocuments, setWorkspaceDocuments] = useState<any[]>([]);
  const [isLoadingDocs, setIsLoadingDocs] = useState(false);

  useEffect(() => {
    const handleAuthChange = () => {
      setActiveWorkspace(getActiveWorkspace());
    };
    window.addEventListener(AUTH_CHANGE_EVENT, handleAuthChange);
    return () => window.removeEventListener(AUTH_CHANGE_EVENT, handleAuthChange);
  }, []);
  const [selectedMessageId, setSelectedMessageId] = useState<string | null>(null);
  const [liveTrace, setLiveTrace] = useState<Record<string, { start: number; end?: number; status: "pending" | "running" | "completed" | "failed" | "skipped"; detail?: string }>>({});
  const [hoveredPhase, setHoveredPhase] = useState<string | null>(null);
  const [streamState, setStreamState] = useState<{ phase: string; detail: string }>({
    phase: "idle",
    detail: "Ready to answer with evals and grounded sources."
  });
  
  const [highlightedCitation, setHighlightedCitation] = useState<number | null>(null);
  const [activeLensTab, setActiveLensTab] = useState<"bi" | "trace" | "signals" | "context">("bi");
  const visibleLensTab = !isAdmin && activeLensTab === "signals" ? "bi" : activeLensTab;

  useEffect(() => {
    if (activeLensTab === "context" && activeWorkspace?.id) {
      setIsLoadingDocs(true);
      apiFetch(`/api/documents/workspace/${activeWorkspace.id}`)
        .then(res => res.json())
        .then(data => {
          setWorkspaceDocuments(Array.isArray(data) ? data : []);
        })
        .catch(err => console.error("Failed to fetch docs", err))
        .finally(() => setIsLoadingDocs(false));
    }
  }, [activeLensTab, activeWorkspace?.id]);

  const scrollRef = useRef<HTMLDivElement>(null);

  const handleFileUpload = async (file: File) => {
    const activeWs = getActiveWorkspace();
    if (!file || !activeWs?.id) return;

    if (file.size > 3.5 * 1024 * 1024) {
      toast.error(`File "${file.name}" exceeds the 3.5MB size limit.`);
      return;
    }

    setIsUploading(true);
    setUploadingFileName(file.name);
    setUploadStatus(null);
    
    setUploadedSessionFiles(prev => [...prev, { name: file.name, status: 'processing' }]);

    const formData = new FormData();
    formData.append("file", file);
    formData.append("workspace_id", activeWs.id);

    try {
      const response = await apiFetch("/api/documents/upload", {
        method: "POST",
        body: formData,
      });

      if (!response.ok) {
        throw new Error("Failed to upload document");
      }

      setUploadStatus({ 
        success: true, 
        message: `File "${file.name}" uploaded successfully and is being processed in the background!` 
      });
      toast.success(`"${file.name}" is being processed!`);
      setTimeout(() => {
        setUploadStatus(null);
        setUploadedSessionFiles(prev => prev.map(f => f.name === file.name ? { ...f, status: 'ready' } : f));
      }, 5000);
    } catch (error) {
      console.error("Upload error:", error);
      const errorMsg = error instanceof Error ? error.message : "Upload failed";
      setUploadStatus({ success: false, message: errorMsg });
      toast.error(errorMsg);
    } finally {
      setIsUploading(false);
      const el = document.getElementById("chat-id-file-upload") as HTMLInputElement;
      if (el) el.value = "";
    }
  };

  const { getRootProps, getInputProps, isDragActive, open } = useDropzone({
    onDrop: (acceptedFiles) => {
      if (acceptedFiles.length > 0) {
        void handleFileUpload(acceptedFiles[0]);
      }
    },
    accept: {
      'application/pdf': ['.pdf'],
      'text/plain': ['.txt', '.md'],
      'application/vnd.openxmlformats-officedocument.wordprocessingml.document': ['.docx']
    },
    maxSize: 3.5 * 1024 * 1024,
    noClick: true,
    onDropRejected: (fileRejections) => {
      fileRejections.forEach((rejection) => {
        rejection.errors.forEach((error) => {
          if (error.code === 'file-too-large') {
            toast.error(`File "${rejection.file.name}" is larger than 3.5MB.`);
          } else if (error.code === 'file-invalid-type') {
            toast.error(`File "${rejection.file.name}" is not a supported format (PDF, TXT, DOCX).`);
          } else {
            toast.error(error.message);
          }
        });
      });
    }
  });

  const fetchConversation = useCallback(async () => {
    setIsConvLoading(true);
    try {
      const response = await apiFetch(`/api/conversations/${id}`);
      if (response.ok) {
        const data = await response.json();
        const parsedMessages = (data.messages || []).map((msg: Message) => {
          if (msg.eval_reasoning) {
            const parts = msg.eval_reasoning.split("\n\n[USER_PROFILE]: ");
            if (parts.length > 1) {
              try {
                const user_profile = JSON.parse(parts[1]);
                let disclaimer = msg.disclaimer;
                if (!disclaimer && msg.tier !== "direct" && ((msg.faithfulness_score !== undefined && msg.faithfulness_score !== null && msg.faithfulness_score < 0.70) || (msg.relevance_score !== undefined && msg.relevance_score !== null && msg.relevance_score < 0.70))) {
                  disclaimer = "⚠️ This response could not be fully verified against internal documents. Please review with caution.";
                }
                return {
                  ...msg,
                  eval_reasoning: parts[0],
                  user_profile,
                  disclaimer
                };
              } catch (e) {
                console.error("Failed to parse user profile", e);
              }
            }
          }
          let disclaimer = msg.disclaimer;
          if (!disclaimer && msg.tier !== "direct" && ((msg.faithfulness_score !== undefined && msg.faithfulness_score !== null && msg.faithfulness_score < 0.70) || (msg.relevance_score !== undefined && msg.relevance_score !== null && msg.relevance_score < 0.70))) {
            disclaimer = "⚠️ This response could not be fully verified against internal documents. Please review with caution.";
          }
          return { ...msg, disclaimer };
        });
        setMessages(parsedMessages);
        setConvTitle(data.title);
        
        if (parsedMessages && parsedMessages.length > 0) {
          const assistantMsgs = parsedMessages.filter((m: Message) => m.answer);
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
          reasoning_mode: false,
          context_files: uploadedSessionFiles.map((f) => f.name)
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
              const responseDisclaimer = data.disclaimer || null;
              const responseUserProfile = data.user_profile || null;

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
                      disclaimer: responseDisclaimer,
                      user_profile: responseUserProfile,
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

      if (!accumulatedAnswer.trim()) {
        const fallback = thinkingLogs.length ? thinkingLogs[thinkingLogs.length - 1] : "No response from assistant.";
        setMessages((prev) =>
          prev.map((msg) => (msg.id === tempAssistantMsgId ? { ...msg, answer: fallback } : msg))
        );
        setStreamState({ phase: "fallback", detail: fallback });
      }

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

  useEffect(() => {
    if (isConvLoading) return;
    const pendingQuery = sessionStorage.getItem("assest_pending_query");
    if (pendingQuery) {
      sessionStorage.removeItem("assest_pending_query");
      const pendingFiles = sessionStorage.getItem("assest_pending_files");
      if (pendingFiles) {
        try {
          setUploadedSessionFiles(JSON.parse(pendingFiles));
        } catch (e) {
          console.error("Failed to parse pending files", e);
        }
        sessionStorage.removeItem("assest_pending_files");
      }
      window.setTimeout(() => {
        void handleSend(pendingQuery);
      }, 100);
    }
  // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [id, isConvLoading]);

  const activeMsg = messages.find(m => m.id === selectedMessageId) || messages[messages.length - 1];

  const getSourcesList = (): CitationSource[] => {
    return activeMsg?.citations || [];
  };

  const handleCitationClick = (citationId: number) => {
    setHighlightedCitation(citationId);
    setActiveLensTab("bi");
    setTimeout(() => setHighlightedCitation(null), 3000);
  };

  return (
    <div className="flex h-full bg-[var(--bg-root)] text-[var(--text-primary)] relative overflow-hidden font-sans animate-fade-in flex-col lg:flex-row">
      {/* Decorative gradient atmosphere */}
      <div className="absolute top-0 left-0 w-[500px] h-[500px] bg-[var(--accent)]/5 rounded-full blur-[120px] pointer-events-none" />

      {/* Left Panel (60% width) */}
      <div className="w-full lg:w-[60%] flex flex-col min-w-0 border-r border-[var(--border-subtle)] h-full relative z-10">
        
        {/* Thread Header */}
        <header className="border-b border-[var(--border-subtle)] px-6 py-4 bg-[var(--bg-sidebar)]/80 backdrop-blur-xl z-20 shrink-0 flex items-center">
          <div className="flex items-center gap-3">
            <span className="label-caps text-[10px] text-[var(--text-muted)]">Thread</span>
            <span className="text-[var(--text-muted)] font-mono">/</span>
            <h2 className="text-sm font-bold text-[var(--text-primary)] max-w-[280px] md:max-w-[400px] truncate font-display">
              {convTitle}
            </h2>
            {getSourcesList().length > 0 && (
              <span className="text-[10px] font-bold text-[var(--accent)] bg-[var(--accent-muted)] border border-[var(--accent)]/20 px-2.5 py-0.5 rounded ml-2 font-mono">
                {getSourcesList().length} CITED
              </span>
            )}
          </div>
        </header>

        {/* Conversation Stream */}
        <div
          ref={scrollRef}
          className="flex-1 overflow-y-auto p-6 md:p-8 space-y-8 pb-36 scrollbar-thin max-w-3xl w-full mx-auto"
        >
          {messages.map((msg, i) => {
            const isAssistant = !!msg.answer;
            const isInspected = selectedMessageId === msg.id;

            return (
              <div key={msg.id || i} className="space-y-3 animate-fade-in">
                {/* User Card */}
                {msg.question && !isAssistant && (
                  <div className="flex flex-col space-y-2 items-end animate-fade-in">
                    {/* Header */}
                    <div className="flex items-center gap-2">
                      <span className="text-[10px] font-mono text-[var(--text-muted)]">
                        {parseUTCDate(msg.created_at).toLocaleTimeString([], { hour: '2-digit', minute: '2-digit' })}
                      </span>
                      <span className="text-xs font-bold text-[var(--text-primary)] uppercase tracking-wide">You</span>
                      <div className="h-6 w-6 rounded bg-[var(--bg-surface-hover)] border border-[var(--border-subtle)] flex items-center justify-center">
                        <User className="h-3 w-3 text-[var(--text-secondary)]" />
                      </div>
                    </div>
                    {/* Body */}
                    <div className="inline-block bg-[var(--bg-surface-hover)] border border-[var(--border-subtle)] text-sm rounded-lg px-4 py-3 text-left text-[var(--text-primary)] leading-relaxed shadow-sm max-w-[85%]">
                      {msg.question}
                    </div>
                  </div>
                )}

                {/* Assistant Card */}
                {isAssistant && (
                  <div 
                    onClick={() => setSelectedMessageId(msg.id)}
                    className={`flex flex-col p-4 rounded-lg border transition-all cursor-pointer relative group space-y-3 ${
                      isInspected 
                        ? "border-[rgba(0,245,255,0.2)] bg-[var(--accent-muted)]/20" 
                        : "border-transparent bg-transparent hover:bg-[var(--bg-surface-hover)]/40"
                    }`}
                  >
                    {isInspected && (
                      <div className="absolute top-0 left-0 w-[3px] h-full bg-[var(--accent)] rounded-l-lg" />
                    )}
                    
                    {/* Header */}
                    <div className="flex items-center justify-between border-b border-[var(--border-subtle)]/40 pb-2">
                      <div className="flex items-center gap-2">
                        <div className="h-6 w-6 rounded bg-[var(--bg-surface)] border border-[var(--border-subtle)] flex items-center justify-center">
                          <Bot className="h-3 w-3 text-[var(--accent)]" />
                        </div>
                        <span className="text-xs font-bold text-[var(--text-primary)] uppercase tracking-wide">Assest Assistant</span>
                        <span className="text-[10px] font-mono text-[var(--text-muted)]">
                          {parseUTCDate(msg.created_at).toLocaleTimeString([], { hour: '2-digit', minute: '2-digit' })}
                        </span>
                        {msg.tier && (
                          <span className="text-[10px] font-bold font-mono text-[var(--text-secondary)] uppercase bg-[var(--bg-surface)] px-2 py-0.5 rounded border border-[var(--border-subtle)]">
                            {msg.tier}
                          </span>
                        )}
                      </div>
                      {isInspected && (
                        <span className="text-[9px] font-bold text-[var(--accent)] uppercase tracking-widest bg-[var(--accent-muted)] border border-[var(--accent)]/30 px-2 py-0.5 rounded font-mono">
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

                    {msg.disclaimer && (
                      <div className="flex items-start gap-2 p-3 rounded-lg border border-[var(--warning)]/20 bg-[var(--warning-muted)]/10 text-xs text-[var(--warning)] font-medium animate-fade-in">
                        <AlertCircle className="h-4 w-4 shrink-0 mt-0.5 text-[var(--warning)]" />
                        <span>{msg.disclaimer}</span>
                      </div>
                    )}

                    {/* Output content */}
                    <div className="text-sm text-[var(--text-secondary)] leading-relaxed pl-1">
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
            <div className="flex gap-4 animate-fade-in p-5 rounded-lg border border-dashed border-[var(--border-subtle)] bg-[var(--bg-surface)]">
              <div className="h-8 w-8 rounded bg-[var(--bg-surface-hover)] border border-[var(--border-subtle)] flex items-center justify-center shrink-0">
                <Cpu className="h-4 w-4 text-[var(--accent)] animate-spin" />
              </div>
              <div className="flex-1 space-y-2">
                <span className="label-caps text-[10px] text-[var(--text-muted)]">Pipeline Processing</span>
                <div className="space-y-1.5">
                  {thinkingLogs.slice(-2).map((log, li) => (
                    <div key={li} className="flex items-center gap-2 text-xs text-[var(--accent)] font-semibold font-mono">
                      <span className="w-1.5 h-1.5 rounded-full bg-[var(--accent)] animate-ping" />
                      <span>{log.toUpperCase()}</span>
                    </div>
                  ))}
                </div>
              </div>
            </div>
          )}
        </div>

        {/* Input Dock */}
        <div className="absolute bottom-0 left-0 right-0 p-6 bg-gradient-to-t from-[var(--bg-root)] via-[var(--bg-root)]/95 to-transparent z-15 shrink-0">
          <div className="max-w-3xl mx-auto space-y-3">
            {isUploading && (
              <div className="flex items-start gap-3 rounded-xl border border-indigo-500/20 bg-indigo-500/5 p-3 text-xs text-indigo-200 backdrop-blur-md animate-pulse">
                <Loader2 className="h-4 w-4 animate-spin text-indigo-400 shrink-0 mt-0.5" />
                <div className="flex-1 min-w-0 space-y-1">
                  <div className="flex items-center justify-between">
                    <span className="font-semibold text-white tracking-wide uppercase text-[9px] font-mono">Ingestion Pipeline</span>
                    <span className="text-[9px] bg-indigo-500/20 text-indigo-300 px-1.5 py-0.5 rounded font-mono">Active</span>
                  </div>
                  <p className="text-[11px] text-indigo-200/90 truncate">
                    Processing: <span className="font-mono text-white font-medium">{uploadingFileName}</span>
                  </p>
                  <p className="text-[9px] text-indigo-400/80">
                    Parsing content, extracting knowledge graphs & building vector indices...
                  </p>
                </div>
              </div>
            )}
            {uploadStatus && (
              <div className={`rounded-lg border px-3 py-2 text-[10px] font-medium animate-fade-in ${
                uploadStatus.success 
                  ? "border-emerald-500/20 bg-emerald-500/5 text-emerald-500" 
                  : "border-rose-500/20 bg-rose-500/5 text-rose-500"
              }`}>
                {uploadStatus.message}
              </div>
            )}
            
            {/* Session Files Context Chips */}
            {uploadedSessionFiles.length > 0 && (
              <div className="flex items-center gap-2 overflow-x-auto pb-1 scrollbar-hide">
                {uploadedSessionFiles.map((f, i) => (
                  <div key={i} className="flex items-center gap-1.5 px-2.5 py-1.5 rounded-lg border border-[var(--border-subtle)] bg-[var(--bg-surface)] shadow-sm shrink-0">
                    <FileText className="h-3 w-3 text-[var(--accent)]" />
                    <span className="text-[11px] font-medium text-[var(--text-primary)] max-w-[150px] truncate">{f.name}</span>
                    {f.status === 'processing' ? (
                      <Loader2 className="h-3 w-3 animate-spin text-[var(--text-muted)]" />
                    ) : (
                      <CheckCircle2 className="h-3 w-3 text-emerald-500" />
                    )}
                  </div>
                ))}
              </div>
            )}
            
            <div 
              {...getRootProps()}
              className={`relative flex items-center gap-2 p-1 rounded-xl border transition-all shadow-[var(--shadow-elevated)] z-0 ${
                isDragActive 
                  ? "border-[var(--accent)] shadow-[0_0_15px_rgba(99,102,241,0.2)] bg-indigo-500/5" 
                  : "border-[var(--border-subtle)] bg-[var(--bg-surface)] focus-within:border-[var(--accent)] focus-within:shadow-[var(--shadow-glow)]"
              }`}
            >
              {isDragActive && (
                <div className="absolute inset-0 z-10 flex items-center justify-center rounded-xl bg-[var(--bg-surface)]/80 backdrop-blur-sm border-2 border-dashed border-[var(--accent)]">
                  <UploadCloud className="h-4 w-4 text-[var(--accent)] mr-2 animate-bounce" />
                  <p className="text-[11px] font-bold text-[var(--text-primary)] uppercase tracking-widest">Drop file here (Max 4.5MB)</p>
                </div>
              )}
              
              <input {...getInputProps()} id="chat-id-file-upload" />
              <button
                type="button"
                onClick={(e) => {
                  e.stopPropagation();
                  open();
                }}
                disabled={isUploading || isLoading}
                title="Upload document"
                className="ml-2 flex h-8 w-8 items-center justify-center rounded-lg border border-[var(--border-subtle)] bg-[var(--bg-root)] text-[var(--text-muted)] hover:border-[var(--accent)] hover:text-[var(--accent)] transition-all disabled:opacity-30 disabled:cursor-not-allowed cursor-pointer shrink-0 relative z-0"
              >
                {isUploading ? (
                  <Loader2 className="h-4 w-4 animate-spin" />
                ) : (
                  <Paperclip className="h-4 w-4" />
                )}
              </button>
              <input
                type="text"
                value={input}
                onChange={(e) => setInput(e.target.value)}
                onKeyDown={(e) => e.key === "Enter" && handleSend()}
                placeholder="Ask follow up..."
                className="composer-input flex-1 bg-transparent py-3.5 px-3 text-sm text-slate-900 placeholder-[var(--text-muted)] focus:outline-none console-input font-medium"
                disabled={isLoading}
              />
              <button
                onClick={() => handleSend()}
                disabled={!input.trim() || isLoading || isUploading}
                className="h-10 px-4 rounded-lg bg-[var(--accent)] hover:bg-[var(--accent-hover)] hover:shadow-[0_0_10px_rgba(0,245,255,0.3)] text-black text-xs font-bold flex items-center justify-center gap-1.5 transition-all shrink-0 cursor-pointer disabled:opacity-30 disabled:cursor-not-allowed font-mono uppercase mr-1"
              >
                {isLoading ? (
                  <Loader2 className="h-4 w-4 animate-spin text-black" />
                ) : (
                  <>
                    <span>Send</span>
                    <Send className="h-3.5 w-3.5 text-black stroke-[2.5]" />
                  </>
                )}
              </button>
            </div>
          </div>
        </div>
      </div>

      {/* Right Observability Panel */}
      <div className="w-full lg:w-[40%] border-t lg:border-t-0 border-l border-[var(--border-subtle)] bg-[var(--bg-sidebar)]/95 backdrop-blur-3xl flex flex-col h-[50vh] lg:h-full overflow-y-auto shrink-0 select-none z-10">
          {/* Header */}
          <div className="p-4 border-b border-[var(--border-subtle)] flex items-center justify-between shrink-0 bg-[var(--bg-surface)]">
            <div className="flex items-center gap-2">
              <Workflow className="h-4 w-4 text-[var(--accent)]" />
              <span className="text-xs font-semibold text-[var(--text-primary)] tracking-wider uppercase">
                {isAdmin ? "Observability HUD" : "Thread Details"}
              </span>
            </div>
            <span className="text-[11px] font-semibold text-[var(--text-muted)] uppercase tracking-wide border border-[var(--border-subtle)] px-2 py-0.5 rounded">
              {isAdmin ? "Active Session" : "User Lens"}
            </span>
          </div>

          {/* Sub-Header / Tab Navigation */}
          <div className={`grid border-b border-[var(--border-subtle)] bg-[var(--bg-root)] text-center ${isAdmin ? "grid-cols-3" : "grid-cols-2"}`}>
            <button
              onClick={() => setActiveLensTab("bi")}
              className={`py-2.5 text-[11px] font-semibold tracking-wider uppercase transition-all cursor-pointer ${
                visibleLensTab === "bi" 
                  ? "text-[var(--accent)] border-b-2 border-[var(--accent)]" 
                  : "text-[var(--text-muted)] hover:text-[var(--text-primary)]"
              }`}
            >
              Quality
            </button>
            <button
              onClick={() => setActiveLensTab("trace")}
              className={`py-2.5 text-[11px] font-semibold tracking-wider uppercase transition-all cursor-pointer ${
                visibleLensTab === "trace" 
                  ? "text-[var(--accent)] border-b-2 border-[var(--accent)]" 
                  : "text-[var(--text-muted)] hover:text-[var(--text-primary)]"
              }`}
            >
              Trace
            </button>
            <button
              onClick={() => setActiveLensTab("context")}
              className={`py-2.5 text-[11px] font-semibold tracking-wider uppercase transition-all cursor-pointer ${
                visibleLensTab === "context" 
                  ? "text-[var(--accent)] border-b-2 border-[var(--accent)]" 
                  : "text-[var(--text-muted)] hover:text-[var(--text-primary)]"
              }`}
            >
              Context
            </button>
            {isAdmin && (
              <button
                onClick={() => setActiveLensTab("signals")}
                className={`py-2.5 text-[11px] font-semibold tracking-wider uppercase transition-all cursor-pointer ${
                  visibleLensTab === "signals" 
                    ? "text-[var(--accent)] border-b-2 border-[var(--accent)]" 
                    : "text-[var(--text-muted)] hover:text-[var(--text-primary)]"
                }`}
              >
                Signals
              </button>
            )}
          </div>

          <div className="p-4 flex-1 space-y-5 overflow-y-auto scrollbar-thin">
            {visibleLensTab === "bi" ? (
              /* Quality Indicators */
              <div className="space-y-4">
                <div className="space-y-2">
                  <span className="text-[12px] font-medium text-[var(--text-muted)] tracking-wider uppercase block">LLM-graded metrics</span>
                  
                  <div className="grid grid-cols-3 gap-2">
                    {/* Faithfulness */}
                    <div className="rounded-xl border border-[var(--border-subtle)] bg-[var(--bg-surface)] p-2 flex flex-col items-center justify-center relative overflow-hidden group">
                      <div className="relative w-16 h-16 flex items-center justify-center mt-1">
                        <svg className="w-full h-full transform -rotate-90">
                          <circle cx="32" cy="32" r="26" className="stroke-zinc-800 fill-transparent" strokeWidth="3" />
                          <circle 
                            cx="32" 
                            cy="32" 
                            r="26" 
                            className="stroke-[var(--success)] fill-transparent transition-all duration-1000 ease-out" 
                            strokeWidth="3.5" 
                            strokeDasharray={2 * Math.PI * 26} 
                            strokeDashoffset={2 * Math.PI * 26 - ((activeMsg?.faithfulness_score !== undefined ? activeMsg.faithfulness_score : 0) * 2 * Math.PI * 26)} 
                            strokeLinecap="round"
                          />
                        </svg>
                        <div className="absolute flex flex-col items-center justify-center">
                          <ShieldCheck className="h-3.5 w-3.5 text-[var(--success)]" />
                          <span className="text-xs font-bold text-[var(--text-primary)] mt-0.5">
                            {activeMsg?.faithfulness_score !== undefined ? `${Math.round(activeMsg.faithfulness_score * 100)}%` : "N/A"}
                          </span>
                        </div>
                      </div>
                      <span className="text-[11px] font-semibold text-[var(--text-muted)] mt-2">Faithful</span>
                    </div>

                    {/* Relevance */}
                    <div className="rounded-xl border border-[var(--border-subtle)] bg-[var(--bg-surface)] p-2 flex flex-col items-center justify-center relative overflow-hidden group">
                      <div className="relative w-16 h-16 flex items-center justify-center mt-1">
                        <svg className="w-full h-full transform -rotate-90">
                          <circle cx="32" cy="32" r="26" className="stroke-zinc-800 fill-transparent" strokeWidth="3" />
                          <circle 
                            cx="32" 
                            cy="32" 
                            r="26" 
                            className="stroke-[var(--accent)] fill-transparent transition-all duration-1000 ease-out" 
                            strokeWidth="3.5" 
                            strokeDasharray={2 * Math.PI * 26} 
                            strokeDashoffset={2 * Math.PI * 26 - ((activeMsg?.relevance_score !== undefined ? activeMsg.relevance_score : 0) * 2 * Math.PI * 26)} 
                            strokeLinecap="round"
                          />
                        </svg>
                        <div className="absolute flex flex-col items-center justify-center">
                          <Award className="h-3.5 w-3.5 text-[var(--accent)]" />
                          <span className="text-xs font-bold text-[var(--text-primary)] mt-0.5">
                            {activeMsg?.relevance_score !== undefined ? `${Math.round(activeMsg.relevance_score * 100)}%` : "N/A"}
                          </span>
                        </div>
                      </div>
                      <span className="text-[11px] font-semibold text-[var(--text-muted)] mt-2">Relevant</span>
                    </div>

                    {/* Grounding */}
                    <div className="rounded-xl border border-[var(--border-subtle)] bg-[var(--bg-surface)] p-2 flex flex-col items-center justify-center relative overflow-hidden group">
                      <div className="relative w-16 h-16 flex items-center justify-center mt-1">
                        <svg className="w-full h-full transform -rotate-90">
                          <circle cx="32" cy="32" r="26" className="stroke-zinc-800 fill-transparent" strokeWidth="3" />
                          <circle 
                            cx="32" 
                            cy="32" 
                            r="26" 
                            className="stroke-indigo-400 fill-transparent transition-all duration-1000 ease-out" 
                            strokeWidth="3.5" 
                            strokeDasharray={2 * Math.PI * 26} 
                            strokeDashoffset={2 * Math.PI * 26 - ((activeMsg?.grounding_score !== undefined ? activeMsg.grounding_score : 0) * 2 * Math.PI * 26)} 
                            strokeLinecap="round"
                          />
                        </svg>
                        <div className="absolute flex flex-col items-center justify-center">
                          <Activity className="h-3.5 w-3.5 text-indigo-400" />
                          <span className="text-xs font-bold text-[var(--text-primary)] mt-0.5">
                            {activeMsg?.grounding_score !== undefined ? `${Math.round(activeMsg.grounding_score * 100)}%` : "N/A"}
                          </span>
                        </div>
                      </div>
                      <span className="text-[11px] font-semibold text-[var(--text-muted)] mt-2">Grounded</span>
                    </div>
                  </div>
                </div>

                {/* Cognitive Profile */}
                {activeMsg?.user_profile && (
                  <div className="space-y-2 animate-fade-in">
                    <span className="text-[12px] font-medium text-[var(--text-muted)] tracking-wider uppercase block">Cognitive Profile</span>
                    <div className="grid grid-cols-3 gap-2">
                      {/* Tone Badge */}
                      <div className="rounded-xl border border-[var(--border-subtle)] bg-[var(--bg-surface)] p-3 flex flex-col items-center justify-center">
                        <span className="text-[10px] font-mono text-[var(--text-muted)] uppercase tracking-wider">Tone</span>
                        <span className={`text-xs font-bold capitalize mt-1 ${
                          activeMsg.user_profile.tone === "frustrated" ? "text-red-600 font-semibold" :
                          activeMsg.user_profile.tone === "confused" ? "text-amber-600 font-semibold" :
                          activeMsg.user_profile.tone === "curious" ? "text-cyan-600 font-semibold" : "text-[var(--text-primary)]"
                        }`}>
                          {activeMsg.user_profile.tone || "neutral"}
                        </span>
                      </div>
                      {/* Complexity Badge */}
                      <div className="rounded-xl border border-[var(--border-subtle)] bg-[var(--bg-surface)] p-3 flex flex-col items-center justify-center">
                        <span className="text-[10px] font-mono text-[var(--text-muted)] uppercase tracking-wider">Complexity</span>
                        <span className={`text-xs font-bold capitalize mt-1 ${
                          activeMsg.user_profile.complexity === "high" ? "text-red-600" :
                          activeMsg.user_profile.complexity === "medium" ? "text-amber-600" : "text-green-600"
                        }`}>
                          {activeMsg.user_profile.complexity || "medium"}
                        </span>
                      </div>
                      {/* Expertise Badge */}
                      <div className="rounded-xl border border-[var(--border-subtle)] bg-[var(--bg-surface)] p-3 flex flex-col items-center justify-center">
                        <span className="text-[10px] font-mono text-[var(--text-muted)] uppercase tracking-wider">Expertise</span>
                        <span className={`text-xs font-bold capitalize mt-1 ${
                          activeMsg.user_profile.expertise === "advanced" ? "text-purple-600" :
                          activeMsg.user_profile.expertise === "intermediate" ? "text-cyan-600" : "text-green-600"
                        }`}>
                          {activeMsg.user_profile.expertise || "intermediate"}
                        </span>
                      </div>
                    </div>
                  </div>
                )}

                {/* Scorer Reasoning */}
                {activeMsg?.eval_reasoning && (
                  <div className="space-y-2">
                    <span className="text-[12px] font-medium text-[var(--text-muted)] tracking-wider uppercase block">Evaluator Rationale</span>
                    <div className="rounded-xl border border-[var(--border-subtle)] bg-[var(--bg-surface)] p-3 text-xs leading-relaxed text-[var(--text-secondary)] space-y-2.5">
                      {activeMsg.eval_reasoning.split("\n\n").map((part, pi) => {
                        const isFaith = part.startsWith("Faithfulness:");
                        const text = part.replace(/^(Faithfulness:|Relevance:)/, "").trim();
                        return (
                          <div key={pi} className="space-y-0.5">
                            <span className="text-[11px] font-semibold text-[var(--text-primary)] uppercase tracking-wider block">
                              {isFaith ? "Faithfulness Verdict" : "Relevance Verdict"}
                            </span>
                            <p>{text}</p>
                          </div>
                        );
                      })}
                    </div>
                  </div>
                )}

                {/* Grounding Source Graph */}
                <div className="rounded-xl border border-[var(--border-subtle)] bg-[var(--bg-surface)] p-4 space-y-3 relative overflow-hidden">
                  <div className="flex items-center justify-between">
                    <span className="text-[12px] font-medium text-[var(--text-muted)] tracking-wider uppercase">Grounding Map</span>
                    <span className="text-xs font-semibold text-[var(--text-muted)]">{getSourcesList().length} links</span>
                  </div>
                  <div className="relative w-full h-[180px] border border-[var(--border-subtle)] bg-[var(--bg-root)] rounded-lg">
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
                              className="stroke-[var(--accent)]/30 stroke-[1.5]"
                              strokeDasharray="3 2"
                            />
                            <circle
                              cx={targetX}
                              cy={targetY}
                              r="6"
                              className="fill-indigo-500/20 stroke-[var(--accent)] stroke-[1.5] cursor-pointer"
                            />
                            <text
                              x={targetX}
                              y={targetY - 9}
                              textAnchor="middle"
                              className="fill-[var(--text-muted)] text-[11px] font-medium"
                            >
                              Doc {src.id}
                            </text>
                          </g>
                        );
                      })}
                      
                      <circle
                        cx="150"
                        cy="90"
                        r="12"
                        className="fill-indigo-500/10 stroke-[var(--accent)] stroke-[1.5] animate-pulse"
                      />
                      <text x="150" y="93" textAnchor="middle" className="fill-[var(--text-primary)] text-[11px] font-bold uppercase tracking-wider">Query</text>
                    </svg>
                  </div>
                </div>

                {/* Grounded Source List */}
                <div className="space-y-2">
                  <span className="text-[12px] font-medium text-[var(--text-muted)] tracking-wider uppercase block">Retrieved Vector Chunks</span>
                  <div className="space-y-1.5">
                    {getSourcesList().length === 0 ? (
                      <div className="text-xs text-[var(--text-muted)] text-center py-6 border border-dashed border-[var(--border-subtle)] rounded-xl">
                        No sources loaded
                      </div>
                    ) : (
                      getSourcesList().map((src, idx) => {
                        const isHighlighted = highlightedCitation === src.id;
                        const confidence = src.confidence !== undefined ? Math.round(src.confidence * 100) : null;
                        return (
                          <div
                            key={idx}
                            className={`flex flex-col p-3 rounded-lg border transition-all ${
                              isHighlighted
                                ? "border-[var(--accent)] bg-[var(--accent-muted)] ring-1 ring-[var(--accent)]/20"
                                : "border-[var(--border-subtle)] bg-[var(--bg-surface)] hover:border-zinc-800"
                            }`}
                          >
                            <div className="flex items-center justify-between mb-1">
                              <div className="flex items-center gap-1.5 overflow-hidden">
                                <span className="flex items-center justify-center w-4 h-4 rounded bg-zinc-900 border border-[var(--border-subtle)] text-white text-[11px] font-bold shrink-0">
                                  {src.id}
                                </span>
                                <BookOpen className="h-3.5 w-3.5 text-[var(--text-secondary)] shrink-0" />
                                <span className="text-xs font-semibold text-[var(--text-primary)] truncate">{src.title}</span>
                              </div>
                              {confidence !== null && (
                                <span className="text-[11px] font-semibold text-[var(--accent)] bg-[var(--accent-muted)] px-1.5 py-0.5 rounded border border-[var(--accent)]/10 shrink-0">
                                  {confidence}% sim
                                </span>
                              )}
                            </div>
                            {src.section_heading && (
                              <span className="text-xs text-[var(--text-muted)] truncate block">
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
            ) : visibleLensTab === "trace" ? (
              <div className="space-y-4 animate-fade-in">
                <div className="flex items-center justify-between">
                  <span className="text-[12px] font-medium text-[var(--text-muted)] tracking-wider uppercase block">Execution Path Telemetry</span>
                  {activeMsg?.response_time_ms && (
                    <span className="text-xs font-semibold text-[var(--accent)] bg-[var(--accent-muted)] px-2 py-0.5 rounded border border-[var(--accent)]/20">
                      {activeMsg.response_time_ms} ms
                    </span>
                  )}
                </div>

                <div className="rounded-xl border border-[var(--border-subtle)] bg-[var(--bg-surface)] p-4 relative overflow-hidden">
                  <div className="relative pl-6 space-y-6">
                    <div className="absolute left-[11px] top-2 bottom-2 w-[1.5px] bg-[var(--border-subtle)] -z-0" />
                    
                    {buildMessageTrace(activeMsg, activeMsg?.id?.startsWith("assistant-") ? liveTrace : undefined).map((phase, idx) => {
                      const isHovered = hoveredPhase === phase.name;
                      
                      let ringColor = "border-[var(--border-subtle)] bg-[var(--bg-root)] text-[var(--text-muted)]";
                      let statusText = "Pending";
                      let statusBadgeColor = "text-[var(--text-muted)] bg-[var(--bg-surface)] border-[var(--border-subtle)]";
                      
                      if (phase.status === "completed") {
                        ringColor = "border-[var(--success-muted)] bg-[var(--success-muted)] text-[var(--success)]";
                        statusText = "Completed";
                        statusBadgeColor = "text-[var(--success)] bg-[var(--success-muted)] border-[var(--success-muted)]";
                      } else if (phase.status === "running") {
                        ringColor = "border-[var(--accent)] bg-indigo-500/10 text-[var(--accent)] animate-pulse shadow-[var(--shadow-glow)]";
                        statusText = "Running";
                        statusBadgeColor = "text-[var(--accent)] bg-[var(--accent-muted)] border-[var(--accent-muted)]";
                      } else if (phase.status === "failed") {
                        ringColor = "border-[var(--danger-muted)] bg-[var(--danger-muted)] text-[var(--danger)]";
                        statusText = "Failed";
                        statusBadgeColor = "text-[var(--danger)] bg-[var(--danger-muted)] border-[var(--danger-muted)]";
                      } else if (phase.status === "skipped") {
                        ringColor = "border-[var(--border-subtle)] bg-[var(--bg-surface-hover)]/30 text-[var(--text-muted)] opacity-60";
                        statusText = "Skipped";
                        statusBadgeColor = "text-[var(--text-muted)] bg-[var(--bg-surface)]/40 border-[var(--border-subtle)]";
                      }

                      return (
                        <div 
                          key={idx} 
                          className="relative flex items-start gap-4 cursor-pointer group"
                          onMouseEnter={() => setHoveredPhase(phase.name)}
                          onMouseLeave={() => setHoveredPhase(null)}
                        >
                          <div className={`relative z-10 w-6 h-6 rounded-full border flex items-center justify-center text-xs font-bold transition-all ${ringColor}`}>
                            {phase.status === "completed" ? (
                              <span>✓</span>
                            ) : phase.status === "failed" ? (
                              <span>✗</span>
                            ) : phase.status === "skipped" ? (
                              <span className="text-[10px] font-semibold text-zinc-750">skip</span>
                            ) : (
                              <span>{idx + 1}</span>
                            )}
                          </div>

                          <div className="flex-1 space-y-1">
                            <div className="flex items-center justify-between">
                              <h4 className={`text-xs font-semibold uppercase tracking-wider ${phase.status === "running" ? "text-[var(--accent)]" : "text-[var(--text-primary)]"}`}>
                                {phase.name}
                              </h4>
                              <div className="flex items-center gap-1.5">
                                {phase.duration_ms !== undefined && (
                                  <span className="text-xs font-semibold text-[var(--text-muted)] font-mono">{phase.duration_ms}ms</span>
                                )}
                                <span className={`text-[10px] font-semibold uppercase tracking-wider px-1.5 py-0.5 rounded border ${statusBadgeColor}`}>
                                  {statusText}
                                </span>
                              </div>
                            </div>
                            
                            <p className="text-xs text-[var(--text-muted)] leading-normal font-normal">
                              {phase.detail || phase.description}
                            </p>

                            {isHovered && (
                              <div className="mt-2 p-3 rounded-lg border border-[var(--accent)]/20 bg-[var(--bg-root)] text-xs font-normal text-[var(--text-secondary)] space-y-2 leading-relaxed animate-fade-in z-20 relative">
                                <div className="flex items-center justify-between border-b border-[var(--border-subtle)] pb-1.5">
                                  <span className="text-[11px] font-semibold uppercase tracking-wider text-[var(--accent)]">Node Inspection</span>
                                  {phase.duration_ms !== undefined && (
                                    <span className="text-xs text-[var(--text-primary)] font-bold">{phase.duration_ms} ms</span>
                                  )}
                                </div>
                                <p className="text-[var(--text-primary)] font-medium">{phase.description}</p>
                                {phase.detail && (
                                  <div className="bg-zinc-950 p-2 rounded border border-[var(--border-subtle)] text-[11px] font-mono text-[var(--text-muted)] whitespace-pre-wrap break-all">
                                    {phase.detail}
                                  </div>
                                )}
                                
                                {phase.metadata && (
                                  <div className="space-y-1.5 pt-1.5 border-t border-[var(--border-subtle)]">
                                    {phase.name === "Routing" && (
                                      <div className="grid grid-cols-2 gap-2">
                                        <div>
                                          <span className="text-[11px] text-[var(--text-muted)] uppercase block font-semibold">Tier</span>
                                          <span className="text-xs text-[var(--text-primary)] uppercase font-bold">{phase.metadata.tier}</span>
                                        </div>
                                        <div>
                                          <span className="text-[11px] text-[var(--text-muted)] uppercase block font-semibold">Intent</span>
                                          <span className="text-xs text-[var(--text-primary)] uppercase font-bold">{phase.metadata.intent}</span>
                                        </div>
                                      </div>
                                    )}
                                    {phase.name === "Retrieval" && (
                                      <div>
                                        <span className="text-[11px] text-[var(--text-muted)] uppercase block font-semibold">Grounding Sources</span>
                                        <span className="text-xs text-[var(--text-primary)] font-bold">{phase.metadata.sources_found} items retrieved</span>
                                      </div>
                                    )}
                                    {phase.name === "Evaluation" && (
                                      <div className="space-y-1.5">
                                        <div className="grid grid-cols-2 gap-2">
                                          <div>
                                            <span className="text-[11px] text-[var(--text-muted)] uppercase block font-semibold">Faithfulness</span>
                                            <span className="text-xs text-[var(--success)] font-bold">
                                              {phase.metadata.faithfulness !== undefined && phase.metadata.faithfulness !== null ? `${Math.round(phase.metadata.faithfulness * 100)}%` : "N/A"}
                                            </span>
                                          </div>
                                          <div>
                                            <span className="text-[11px] text-[var(--text-muted)] uppercase block font-semibold">Relevance</span>
                                            <span className="text-xs text-[var(--accent)] font-bold">
                                              {phase.metadata.relevance !== undefined && phase.metadata.relevance !== null ? `${Math.round(phase.metadata.relevance * 100)}%` : "N/A"}
                                            </span>
                                          </div>
                                        </div>
                                        {phase.metadata.reasoning && (
                                          <div>
                                            <span className="text-[11px] text-[var(--text-muted)] uppercase block font-semibold">Rationale</span>
                                            <span className="text-xs text-[var(--text-secondary)] leading-normal block italic">
                                              {phase.metadata.reasoning.split("\n\n")[0]?.replace(/^(Faithfulness:|Relevance:)/, "")?.trim() || ""}
                                            </span>
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
            ) : visibleLensTab === "context" ? (
              <div className="space-y-4">
                <div className="space-y-2">
                  <span className="text-[12px] font-medium text-[var(--text-muted)] tracking-wider uppercase flex items-center gap-2">
                    <Database className="h-3.5 w-3.5" /> Workspace Knowledge Base
                  </span>
                  <p className="text-[11px] text-[var(--text-muted)]">
                    These documents have been ingested and are available for the AI to retrieve during this conversation.
                  </p>
                </div>
                
                {isLoadingDocs ? (
                  <div className="flex items-center justify-center p-8">
                    <Loader2 className="h-5 w-5 animate-spin text-[var(--accent)]" />
                  </div>
                ) : workspaceDocuments.length === 0 ? (
                  <div className="text-center p-8 border border-[var(--border-subtle)] border-dashed rounded-xl bg-[var(--bg-surface)]">
                    <p className="text-xs text-[var(--text-muted)]">No documents available in this workspace.</p>
                  </div>
                ) : (
                  <div className="space-y-2">
                    {workspaceDocuments.map((doc, i) => (
                      <div key={doc.id || i} className="p-3 rounded-lg border border-[var(--border-subtle)] bg-[var(--bg-surface)] flex flex-col gap-2 transition-all hover:border-[var(--border-focus)]">
                        <div className="flex items-start justify-between gap-3">
                          <div className="flex items-center gap-2 min-w-0">
                            <FileText className="h-4 w-4 text-[var(--accent)] shrink-0" />
                            <span className="text-sm font-semibold text-[var(--text-primary)] truncate">{doc.title || doc.source_url}</span>
                          </div>
                          {doc.is_active && <span className="shrink-0 text-[9px] font-bold uppercase tracking-wider text-emerald-500 bg-emerald-500/10 px-1.5 py-0.5 rounded">Active</span>}
                        </div>
                        <div className="flex items-center gap-4 text-[10px] text-[var(--text-muted)]">
                          <span className="font-mono">{new Date(doc.last_ingested_at).toLocaleDateString()}</span>
                          {doc.chunk_count > 0 && <span className="font-mono">{doc.chunk_count} Chunks</span>}
                        </div>
                      </div>
                    ))}
                  </div>
                )}
              </div>
            ) : visibleLensTab === "signals" && isAdmin ? (
              <div className="space-y-4">
                <SystemSignalsPanel />
              </div>
            ) : (
              <div className="rounded-xl border border-[var(--border-subtle)] bg-[var(--bg-surface)] p-4 text-sm text-[var(--text-secondary)] leading-relaxed">
                User mode keeps the lens simple: compare grounding, trace the response path, and review citations without exposing infra noise.
              </div>
            )}
          </div>
        </div>
      </div>
  );
}
