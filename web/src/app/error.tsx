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
    <div className="flex h-full min-h-[420px] items-center justify-center bg-[var(--bg-root)] px-6 text-[var(--text-primary)]">
      <div className="w-full max-w-md rounded-xl border border-[var(--danger-muted)] bg-[var(--danger-muted)] p-6 shadow-[var(--shadow-card)]">
        <div className="flex items-start gap-3">
          <AlertTriangle className="mt-0.5 h-5 w-5 shrink-0 text-[var(--danger)]" />
          <div className="space-y-2">
            <h1 className="text-sm font-bold text-white">
              Workspace view failed
            </h1>
            <p className="text-xs leading-relaxed text-[var(--text-secondary)]">
              The frontend caught a render or data loading error. Retry the route, then check the server logs with digest{" "}
              <span className="font-mono text-white">{error.digest || "unavailable"}</span>.
            </p>
          </div>
        </div>
        <button
          type="button"
          onClick={() => unstable_retry()}
          className="mt-5 inline-flex items-center gap-1.5 rounded-xl bg-[var(--accent)] hover:bg-[var(--accent-hover)] text-white px-4 py-2 text-xs font-semibold transition-colors shadow-sm cursor-pointer"
        >
          <RotateCcw className="h-4 w-4" />
          <span>Retry</span>
        </button>
      </div>
    </div>
  );
}
