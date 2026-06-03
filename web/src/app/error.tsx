"use client";

import { useEffect } from "react";
import { AlertTriangle, RotateCcw } from "lucide-react";

export default function Error({
  error,
  unstable_retry,
}: {
  error: Error & { digest?: string };
  unstable_retry: () => void;
}) {
  useEffect(() => {
    console.error("Route error boundary captured", error);
  }, [error]);

  return (
    <div className="flex h-full min-h-[420px] items-center justify-center bg-background px-6 text-foreground">
      <div className="w-full max-w-md rounded-xl border border-red-500/20 bg-red-500/5 p-6">
        <div className="flex items-start gap-3">
          <AlertTriangle className="mt-0.5 h-5 w-5 shrink-0 text-red-300" />
          <div className="space-y-2">
            <h1 className="text-sm font-black uppercase tracking-widest text-white">
              Workspace view failed
            </h1>
            <p className="text-xs leading-relaxed text-zinc-400">
              The frontend caught a render or data loading error. Retry the route, then check the server logs with digest{" "}
              <span className="font-mono text-zinc-200">{error.digest || "unavailable"}</span>.
            </p>
          </div>
        </div>
        <button
          type="button"
          onClick={() => unstable_retry()}
          className="mt-5 inline-flex items-center gap-2 rounded-lg border border-white/10 bg-white px-3 py-2 text-[10px] font-black uppercase tracking-widest text-black transition-colors hover:bg-primary"
        >
          <RotateCcw className="h-3.5 w-3.5" />
          Retry
        </button>
      </div>
    </div>
  );
}

