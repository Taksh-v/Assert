import { Loader2 } from "lucide-react";

export default function Loading() {
  return (
    <div className="flex h-full min-h-[420px] items-center justify-center bg-background text-foreground">
      <div className="flex items-center gap-3 rounded-xl border border-white/[0.04] bg-white/[0.02] px-4 py-3">
        <Loader2 className="h-4 w-4 animate-spin text-primary" />
        <span className="text-[10px] font-black uppercase tracking-widest text-zinc-400">
          Loading workspace
        </span>
      </div>
    </div>
  );
}

