"use client";

import { useState, useRef, useEffect, useCallback } from "react";
import { useParams } from "next/navigation";
import { Bot, User, Loader2, Send, Paperclip } from "lucide-react";

interface Message {
  id: string;
  question: string;
  answer: string;
  sources: { title: string; url: string }[];
  created_at: string;
}

export default function ChatIdPage() {
  const { id } = useParams();
  const [messages, setMessages] = useState<Message[]>([]);
  const [input, setInput] = useState("");
  const [isLoading, setIsLoading] = useState(false);
  const [convTitle, setConvTitle] = useState("Conversation");
  const scrollRef = useRef<HTMLDivElement>(null);

  const fetchConversation = useCallback(async () => {
    try {
      const response = await fetch(`http://localhost:8000/api/conversations/${id}`);
      if (response.ok) {
        const data = await response.json();
        setMessages(data.messages);
        setConvTitle(data.title);
      }
    } catch (error) {
      console.error("Failed to fetch conversation:", error);
    }
  }, [id]);

  useEffect(() => {
    // eslint-disable-next-line react-hooks/set-state-in-effect
    void fetchConversation();
  }, [fetchConversation]);

  useEffect(() => {
    if (scrollRef.current) {
      scrollRef.current.scrollTop = scrollRef.current.scrollHeight;
    }
  }, [messages]);

  const handleSend = async () => {
    if (!input.trim() || isLoading) return;

    const userQuestion = input;
    setInput("");
    setIsLoading(true);

    try {
      const response = await fetch("http://localhost:8000/api/query", {
        method: "POST",
        headers: {
          "Content-Type": "application/json",
          "X-API-Key": "assest_secret_key"
        },
        body: JSON.stringify({
          question: userQuestion,
          workspace_id: "default-workspace",
          conversation_id: id
        })
      });

      if (response.ok) {
        const data = await response.json();
        // Optimistically update or just re-fetch
        // For simplicity, let's just add the new message to state
        const newMessage: Message = {
          id: data.query_id,
          question: userQuestion,
          answer: data.answer,
          sources: data.sources,
          created_at: new Date().toISOString()
        };
        setMessages((prev) => [...prev, newMessage]);
      }
    } catch (error) {
      console.error("Error sending query:", error);
    } finally {
      setIsLoading(false);
    }
  };

  return (
    <div className="flex flex-col h-full bg-background relative overflow-hidden">
      {/* Dynamic Background */}
      <div className="absolute inset-0 bg-[radial-gradient(circle_at_50%_-20%,var(--color-primary),transparent_70%)] opacity-[0.03] pointer-events-none" />

      {/* Header */}
      <header className="flex h-16 items-center justify-between border-b px-8 bg-background/50 backdrop-blur-xl z-10">
        <div className="flex items-center gap-3">
          <MessageSquare className="h-4 w-4 text-primary" />
          <h2 className="text-sm font-bold truncate max-w-[300px]">{convTitle}</h2>
        </div>
        <div className="flex items-center gap-4">
          <div className="flex -space-x-2">
            {[1, 2].map((i) => (
              <div key={i} className="h-6 w-6 rounded-full border-2 border-background bg-accent" />
            ))}
          </div>
          <button className="text-xs font-bold text-primary hover:underline">Share</button>
        </div>
      </header>

      {/* Chat Area */}
      <div 
        ref={scrollRef}
        className="flex-1 overflow-y-auto p-8 space-y-12 pb-32"
      >
        {messages.map((msg) => (
          <div key={msg.id} className="max-w-4xl mx-auto space-y-8 animate-fade-in">
            {/* User Message */}
            <div className="flex gap-4 justify-end">
              <div className="bg-primary/10 text-foreground px-6 py-4 rounded-2xl rounded-tr-sm max-w-[80%] shadow-sm border border-primary/10">
                <p className="text-sm leading-relaxed">{msg.question}</p>
              </div>
              <div className="h-8 w-8 rounded-lg bg-accent flex items-center justify-center shrink-0">
                <User className="h-5 w-5 text-muted-foreground" />
              </div>
            </div>

            {/* Assistant Message */}
            <div className="flex gap-4">
              <div className="h-8 w-8 rounded-lg bg-primary text-primary-foreground flex items-center justify-center shrink-0 shadow-lg shadow-primary/20">
                <Bot className="h-5 w-5" />
              </div>
              <div className="space-y-6 flex-1">
                <div className="prose dark:prose-invert max-w-none text-sm leading-7">
                  {msg.answer}
                </div>
                
                {msg.sources && msg.sources.length > 0 && (
                  <div className="grid grid-cols-1 md:grid-cols-2 gap-3 pt-4">
                    {msg.sources.map((s, si) => (
                      <a 
                        key={si}
                        href={s.url}
                        target="_blank"
                        className="group flex items-center gap-3 p-3 rounded-xl bg-accent/30 border border-border/50 hover:border-primary/50 hover:bg-accent/50 transition-all duration-300"
                      >
                        <div className="h-8 w-8 rounded-lg bg-background flex items-center justify-center border border-border group-hover:border-primary/20 transition-colors">
                          <Paperclip className="h-4 w-4 text-muted-foreground" />
                        </div>
                        <div className="flex flex-col overflow-hidden">
                          <span className="text-xs font-bold truncate">{s.title}</span>
                          <span className="text-[10px] text-muted-foreground truncate">{s.url}</span>
                        </div>
                      </a>
                    ))}
                  </div>
                )}
              </div>
            </div>
          </div>
        ))}
        
        {isLoading && (
          <div className="max-w-4xl mx-auto flex gap-4 animate-fade-in">
            <div className="h-8 w-8 rounded-lg bg-primary text-primary-foreground flex items-center justify-center shrink-0">
              <Loader2 className="h-5 w-5 animate-spin" />
            </div>
            <div className="space-y-3 flex-1">
              <div className="h-4 w-3/4 bg-accent/50 rounded animate-pulse" />
              <div className="h-4 w-1/2 bg-accent/50 rounded animate-pulse" />
            </div>
          </div>
        )}
      </div>

      {/* Input Field */}
      <div className="absolute bottom-0 left-0 right-0 p-8 bg-gradient-to-t from-background via-background/90 to-transparent">
        <div className="max-w-4xl mx-auto">
          <div className="relative group">
            <div className="absolute inset-0 bg-primary/5 rounded-[2rem] blur-xl group-focus-within:bg-primary/10 transition-all" />
            <div className="relative flex items-center gap-2 p-2 rounded-[2rem] border border-border/50 bg-card/50 backdrop-blur-2xl shadow-2xl focus-within:border-primary/30 transition-all">
              <button className="p-3 rounded-full hover:bg-accent text-muted-foreground transition-colors">
                <Paperclip className="h-5 w-5" />
              </button>
              <input 
                type="text"
                value={input}
                onChange={(e) => setInput(e.target.value)}
                onKeyDown={(e) => e.key === "Enter" && handleSend()}
                placeholder="Message Assest Brain..."
                className="flex-1 bg-transparent py-4 px-2 text-sm focus:outline-none"
              />
              <button 
                onClick={handleSend}
                disabled={!input.trim() || isLoading}
                className="h-12 w-12 rounded-full bg-primary text-primary-foreground flex items-center justify-center hover:scale-105 active:scale-95 disabled:opacity-50 disabled:hover:scale-100 shadow-lg shadow-primary/20 transition-all"
              >
                <Send className="h-5 w-5" />
              </button>
            </div>
          </div>
          <p className="text-center text-[10px] text-muted-foreground pt-4 font-medium uppercase tracking-tighter">
            AI-Generated response. Verify sources for accuracy.
          </p>
        </div>
      </div>
    </div>
  );
}

// Helper icons
import { MessageSquare } from "lucide-react";
