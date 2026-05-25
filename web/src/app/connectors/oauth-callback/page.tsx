"use client";

import { Suspense, useEffect, useState } from "react";
import { useSearchParams } from "next/navigation";
import { CheckCircle2, XCircle, Loader2 } from "lucide-react";

/**
 * OAuth Callback Landing Page
 * 
 * This page is loaded inside the OAuth popup window after the backend
 * redirects back. It sends a postMessage to the opener (parent) window
 * with the connection result and auto-closes.
 * 
 * If the opener window is lost (e.g., user closed the parent tab),
 * it shows a fallback UI with a redirect link.
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
      // Send message to the opener window (SourceSetupModal)
      if (window.opener) {
        window.opener.postMessage({
          type: "oauth-callback",
          status: "success",
          source_type: connected,
          connector_id: connectorId,
        }, "*");

        // Auto-close after brief display
        setTimeout(() => window.close(), 1500);
      }
      return;
    }

    if (!error) {
      // Wait briefly for any server redirect
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
    <div className="flex items-center justify-center min-h-screen bg-background">
      <div className="glass-card p-12 rounded-[2.5rem] text-center max-w-md space-y-6">
        {status === "loading" && (
          <>
            <Loader2 className="w-12 h-12 text-blue-400 animate-spin mx-auto" />
            <h2 className="text-xl font-bold text-white">Connecting...</h2>
            <p className="text-sm text-zinc-500">{message}</p>
          </>
        )}

        {status === "success" && (
          <>
            <div className="relative w-16 h-16 mx-auto">
              <div className="absolute inset-0 bg-green-500/30 blur-2xl rounded-full animate-pulse" />
              <CheckCircle2 className="w-16 h-16 text-green-400 relative" />
            </div>
            <h2 className="text-xl font-bold text-white">Connected!</h2>
            <p className="text-sm text-zinc-500">{message}</p>
            <p className="text-xs text-zinc-600">This window will close automatically...</p>
          </>
        )}

        {status === "error" && (
          <>
            <XCircle className="w-16 h-16 text-red-400 mx-auto" />
            <h2 className="text-xl font-bold text-white">Connection Failed</h2>
            <p className="text-sm text-red-400">{message}</p>
            <a 
              href="/connectors" 
              className="inline-block px-6 py-3 rounded-xl bg-zinc-800 text-white text-sm font-bold hover:bg-zinc-700 transition-colors"
            >
              Back to Connectors
            </a>
          </>
        )}
      </div>
    </div>
  );
}
