import { useState, useRef, useEffect, useCallback } from "react";
import { apiFetch } from "./auth";

export interface SyncRun {
  id: string;
  status: "queued" | "running" | "completed" | "completed_with_errors" | "failed" | "cancelled";
  stats?: Record<string, unknown>;
  error?: string | null;
}

export interface PollingOptions {
  onSuccess?: (run: SyncRun) => void;
  onError?: (error: string) => void;
  onProgress?: (progressText: string, run: SyncRun) => void;
}

export function useSyncRunPolling() {
  const [isPolling, setIsPolling] = useState(false);
  const [progress, setProgress] = useState("");
  const [error, setError] = useState<string | null>(null);
  const abortControllerRef = useRef<AbortController | null>(null);

  const stopPolling = useCallback(() => {
    if (abortControllerRef.current) {
      abortControllerRef.current.abort();
      abortControllerRef.current = null;
    }
    setIsPolling(false);
  }, []);

  const startPolling = useCallback((syncRunId: string, options?: PollingOptions) => {
    // Stop any existing polling first
    stopPolling();

    const controller = new AbortController();
    abortControllerRef.current = controller;
    setIsPolling(true);
    setError(null);
    setProgress("Queued...");

    const runPoll = async () => {
      const terminal = new Set(["completed", "completed_with_errors", "failed", "cancelled"]);
      const signal = controller.signal;

      for (let attempt = 0; attempt < 180; attempt += 1) {
        if (signal.aborted) return;

        try {
          const statusRes = await apiFetch(`/api/sync-runs/${syncRunId}`, { signal });
          if (signal.aborted) return;

          if (!statusRes.ok) {
            const errorData = await statusRes.json().catch(() => ({}));
            if (signal.aborted) return;
            const errStr = errorData.detail || "Unable to check sync status";
            setError(errStr);
            options?.onError?.(errStr);
            setIsPolling(false);
            return;
          }

          const syncRun = await statusRes.json() as SyncRun;
          if (signal.aborted) return;

          let currentProgress = "";
          if (syncRun.status === "queued") {
            currentProgress = "Sync queued...";
          } else if (syncRun.status === "running") {
            currentProgress = "Processing documents through the ingestion pipeline...";
          }
          setProgress(currentProgress);
          options?.onProgress?.(currentProgress, syncRun);

          if (terminal.has(syncRun.status)) {
            setIsPolling(false);
            if (syncRun.status === "completed" || syncRun.status === "completed_with_errors") {
              options?.onSuccess?.(syncRun);
            } else {
              const errStr = syncRun.error || "Sync failed before completion";
              setError(errStr);
              options?.onError?.(errStr);
            }
            return;
          }
        } catch (err: unknown) {
          if (signal.aborted) return;
          const errStr = err instanceof Error ? err.message : String(err);
          setError(errStr);
          options?.onError?.(errStr);
          setIsPolling(false);
          return;
        }

        // Wait 1500ms before next attempt, respecting abort signal
        await new Promise<void>((resolve, reject) => {
          const timeoutId = setTimeout(() => {
            signal.removeEventListener("abort", onAbort);
            resolve();
          }, 1500);

          function onAbort() {
            clearTimeout(timeoutId);
            reject(new Error("aborted"));
          }

          signal.addEventListener("abort", onAbort);
        }).catch(() => {});
      }

      if (!signal.aborted) {
        const timeoutError = "Sync is still running in the background. Check status on connectors page.";
        setError(timeoutError);
        options?.onError?.(timeoutError);
        setIsPolling(false);
      }
    };

    void runPoll();
  }, [stopPolling]);

  // Clean up polling on unmount
  useEffect(() => {
    return () => {
      if (abortControllerRef.current) {
        abortControllerRef.current.abort();
      }
    };
  }, []);

  return {
    isPolling,
    progress,
    error,
    startPolling,
    stopPolling,
  };
}
