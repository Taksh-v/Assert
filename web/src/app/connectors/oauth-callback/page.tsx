"use client";

import { Suspense, useEffect, useState } from "react";
import { useSearchParams } from "next/navigation";
import { XCircle, Loader2, Brain } from "lucide-react";
import ConnectorIcon from "@/components/ConnectorIcon";

/**
 * OAuth Callback Landing Page
 * 
 * This page is loaded inside the OAuth popup window after the backend
 * redirects back. It sends a postMessage to the opener (parent) window
 * with the connection result and auto-closes.
 */
export default function OAuthCallbackPage() {
  return (
    <Suspense fallback={null}>
      <OAuthCallbackContent />
    </Suspense>
  );
}

function OAuthCallbackContent() {
  const searchParams = useSearchParams();
  const connected = searchParams.get("connected");
  const connectorId = searchParams.get("connector_id");
  const error = searchParams.get("error");
  const initialStatus: "loading" | "success" | "error" = error ? "error" : connected && connectorId ? "success" : "loading";
  const initialMessage = error || (connected ? `Successfully connected to ${connected}!` : "Processing connection...");
  const [status, setStatus] = useState<"loading" | "success" | "error">(initialStatus);
  const [message, setMessage] = useState(initialMessage);

  useEffect(() => {
    if (connected && connectorId) {
      if (window.opener) {
        window.opener.postMessage({
          type: "oauth-callback",
          status: "success",
          source_type: connected,
          connector_id: connectorId,
        }, "*");

        setTimeout(() => window.close(), 1500);
      }
      return;
    }

    if (!error) {
      const timer = setTimeout(() => {
        if (status === "loading") {
          setStatus("error");
          setMessage("Connection timed out. Please try again.");
        }
      }, 10000);
      return () => clearTimeout(timer);
    }
  }, [connected, connectorId, error, status]);

  return (
    <div className="relative flex min-h-screen items-center justify-center bg-slate-950 p-6 overflow-hidden">
      <div className="pointer-events-none absolute right-1/4 top-1/4 h-80 w-80 rounded-full bg-blue-500/10 blur-3xl" />
      <div className="pointer-events-none absolute left-1/4 bottom-1/4 h-80 w-80 rounded-full bg-emerald-500/5 blur-3xl" />

      <div className="w-full max-w-md overflow-hidden rounded-3xl border border-slate-800 bg-slate-900/40 backdrop-blur-md p-8 md:p-12 text-center space-y-6 shadow-2xl relative z-10 animate-fade-in">
        {status === "loading" && (
          <div className="space-y-4">
            <div className="relative mx-auto h-20 w-20 flex items-center justify-center rounded-2xl border border-slate-800 bg-slate-950 text-slate-100 shadow-xl">
              <ConnectorIcon type={connected || "loading"} className="h-10 w-10 animate-pulse text-blue-500" />
              <div className="absolute -bottom-1 -right-1 flex h-6 w-6 items-center justify-center rounded-full border border-slate-800 bg-slate-900 shadow">
                <Loader2 className="h-3 w-3 animate-spin text-blue-500" />
              </div>
            </div>
            <div className="space-y-2">
              <h2 className="text-xl font-semibold text-slate-100 tracking-tight">Authorizing Application</h2>
              <p className="text-sm text-slate-400 leading-relaxed">{message}</p>
            </div>
          </div>
        )}

        {status === "success" && (
          <div className="space-y-4">
            <div className="flex items-center justify-center gap-4 py-4 w-full">
              <div className="flex h-14 w-14 shrink-0 items-center justify-center rounded-2xl border border-slate-800 bg-slate-950 shadow-md">
                <Brain className="h-6 w-6 text-blue-500" />
              </div>
              
              <div className="relative w-16 h-[3px] bg-slate-800 rounded-full overflow-hidden shrink-0">
                <div className="absolute inset-0 bg-emerald-500" />
              </div>

              <div className="flex h-14 w-14 shrink-0 items-center justify-center rounded-2xl border border-emerald-500/20 bg-slate-950 text-emerald-400 shadow-md shadow-emerald-500/5">
                <ConnectorIcon type={connected || ""} className="h-6 w-6" />
              </div>
            </div>
            <div className="space-y-2">
              <h2 className="text-xl font-semibold text-slate-100 tracking-tight">Connection Complete</h2>
              <p className="text-sm text-slate-300 leading-relaxed">
                Successfully authorized <span className="font-semibold text-white capitalize">{connected}</span>.
              </p>
              <p className="font-mono text-[9px] uppercase tracking-wider text-slate-500">This window will close automatically...</p>
            </div>
          </div>
        )}

        {status === "error" && (
          <div className="space-y-4">
            <div className="relative mx-auto h-16 w-16 flex items-center justify-center rounded-2xl border border-rose-950 bg-slate-950 text-rose-500 shadow-xl">
              <XCircle className="h-8 w-8" />
            </div>
            <div className="space-y-4">
              <div className="space-y-2">
                <h2 className="text-xl font-semibold text-slate-100 tracking-tight">Connection Failed</h2>
                <p className="text-sm text-rose-400 leading-relaxed">{message}</p>
              </div>
              <button 
                onClick={() => window.close()}
                className="inline-flex h-10 items-center justify-center rounded-xl bg-slate-900 border border-slate-800 px-6 text-xs font-semibold text-slate-200 hover:bg-slate-800 transition"
              >
                Close Window
              </button>
            </div>
          </div>
        )}
      </div>
    </div>
  );
}
