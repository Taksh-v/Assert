import { Loader2 } from "lucide-react";

export default function Loading() {
  return (
    <div className="flex h-full min-h-[420px] items-center justify-center bg-[var(--bg-root)] text-[var(--text-primary)]">
      <div className="flex items-center gap-3 rounded-xl border border-[var(--border-subtle)] bg-[var(--bg-surface)] px-4 py-3 shadow-[var(--shadow-card)]">
        <Loader2 className="h-4 w-4 animate-spin text-[var(--accent)]" />
        <span className="text-xs font-semibold text-[var(--text-secondary)]">
          Loading workspace...
        </span>
      </div>
    </div>
  );
}
