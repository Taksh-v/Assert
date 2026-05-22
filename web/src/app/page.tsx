"use client";

import { useState, useRef, useEffect } from "react";
import { Send, Bot, User, Loader2, Sparkles } from "lucide-react";
import { apiFetch, getActiveWorkspace } from "@/lib/auth";

interface Message {
  role: "user" | "assistant";
  content: string;
  sources?: { title: string; url: string }[];
}

export default function ChatPage() {
  const [messages, setMessages] = useState<Message[]>([]);
  const [input, setInput] = useState("");
  const [isLoading, setIsLoading] = useState(false);
  const scrollRef = useRef<HTMLDivElement>(null);

  useEffect(() => {
    if (scrollRef.current) {
      scrollRef.current.scrollTop = scrollRef.current.scrollHeight;
    }
  }, [messages]);

  const handleSend = async () => {
    if (!input.trim() || isLoading) return;

    const userMessage: Message = { role: "user", content: input };
    setMessages((prev) => [...prev, userMessage]);
    setInput("");
    setIsLoading(true);

    try {
      const activeWs = getActiveWorkspace();
      const workspaceId = activeWs?.id || "default-workspace";

      const response = await apiFetch("/api/query", {
        method: "POST",
        body: JSON.stringify({
          question: input,
          workspace_id: workspaceId
        })
      });

      const data = await response.json();

      const assistantMessage: Message = {
        role: "assistant",
        content: data.answer,
        sources: data.sources
      };

      setMessages((prev) => [...prev, assistantMessage]);
    } catch (error) {
      console.error("Error querying backend:", error);
      setMessages((prev) => [...prev, {
        role: "assistant",
        content: "Sorry, I'm having trouble connecting to the brain. Make sure the backend is running."
      }]);
    } finally {
      setIsLoading(false);
    }
  };

  return (
    <div className="flex flex-col h-full bg-background">
      {/* Header */}
      <header className="flex h-16 items-center justify-between border-b px-8 bg-card/10 backdrop-blur-md">
        <div className="flex items-center gap-2">
          <Sparkles className="h-5 w-5 text-primary" />
          <h2 className="text-lg font-semibold">Knowledge Chat</h2>
        </div>
        <div className="text-sm text-muted">
          v0.1.0-alpha
        </div>
      </header>

      {/* Messages */}
      <div
        ref={scrollRef}
        className="flex-1 overflow-y-auto p-8 space-y-8"
      >
        {messages.length === 0 ? (
          <div className="flex flex-col items-center justify-center h-full text-center space-y-4">
            <div className="h-16 w-16 rounded-2xl bg-primary/10 flex items-center justify-center">
              <Bot className="h-8 w-8 text-primary" />
            </div>
            <div className="space-y-2">
              <h3 className="text-2xl font-bold">Ask anything about your company</h3>
              <p className="text-muted max-w-sm">
                I can search through Notion, Google Drive, and Slack to find exactly what you need.
              </p>
            </div>
            <div className="grid grid-cols-2 gap-4 pt-8">
              {["What is the refund policy?", "How do I set up my dev environment?", "Who is the lead for Project Phoenix?", "Show me the latest marketing assets"].map((q) => (
                <button
                  key={q}
                  onClick={() => setInput(q)}
                  className="px-4 py-3 text-sm rounded-xl border bg-card hover:bg-accent transition-colors text-left"
                >
                  {q}
                </button>
              ))}
            </div>
          </div>
        ) : (
          messages.map((msg, i) => (
            <div key={i} className={`flex gap-4 ${msg.role === "assistant" ? "bg-accent/50 -mx-8 px-8 py-8" : ""}`}>
              <div className={`h-8 w-8 rounded-lg flex items-center justify-center shrink-0 ${msg.role === "assistant" ? "bg-primary text-primary-foreground" : "bg-zinc-200 dark:bg-zinc-800"
                }`}>
                {msg.role === "assistant" ? <Bot className="h-5 w-5" /> : <User className="h-5 w-5" />}
              </div>
              <div className="space-y-4 max-w-3xl">
                <div className="prose dark:prose-invert leading-relaxed">
                  {msg.content}
                </div>
                {msg.sources && msg.sources.length > 0 && (
                  <div className="flex flex-wrap gap-2 pt-2">
                    {msg.sources.map((s, si) => (
                      <a
                        key={si}
                        href={s.url}
                        target="_blank"
                        className="text-xs px-2 py-1 rounded bg-background border hover:border-primary transition-colors flex items-center gap-1"
                      >
                        <span className="w-1 h-1 rounded-full bg-primary" />
                        {s.title}
                      </a>
                    ))}
                  </div>
                )}
              </div>
            </div>
          ))
        )}
        {isLoading && (
          <div className="flex gap-4 bg-accent/50 -mx-8 px-8 py-8">
            <div className="h-8 w-8 rounded-lg bg-primary text-primary-foreground flex items-center justify-center">
              <Loader2 className="h-5 w-5 animate-spin" />
            </div>
            <div className="text-muted italic animate-pulse">
              Consulting the brain...
            </div>
          </div>
        )}
      </div>

      {/* Input */}
      <div className="p-8 border-t bg-card/20 backdrop-blur-xl">
        <div className="max-w-4xl mx-auto relative">
          <input
            type="text"
            value={input}
            onChange={(e) => setInput(e.target.value)}
            onKeyDown={(e) => e.key === "Enter" && handleSend()}
            placeholder="Ask a question..."
            className="w-full pl-6 pr-16 py-4 rounded-2xl border bg-background shadow-xl shadow-primary/5 focus:outline-none focus:ring-2 focus:ring-primary/20 transition-all"
          />
          <button
            onClick={handleSend}
            disabled={!input.trim() || isLoading}
            className="absolute right-3 top-3 h-10 w-10 rounded-xl bg-primary text-primary-foreground flex items-center justify-center hover:scale-105 active:scale-95 disabled:opacity-50 disabled:hover:scale-100 transition-all"
          >
            <Send className="h-5 w-5" />
          </button>
        </div>
        <p className="text-center text-[10px] text-muted pt-4">
          Assest can make mistakes. Verify important information.
        </p>
      </div>
    </div>
  );
}
