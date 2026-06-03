import Link from "next/link";
import { Home } from "lucide-react";

export default function NotFound() {
  return (
    <div className="flex h-full min-h-[420px] items-center justify-center bg-background px-6 text-foreground">
      <div className="w-full max-w-sm rounded-xl border border-white/[0.06] bg-white/[0.02] p-6 text-center">
        <h1 className="text-sm font-black uppercase tracking-widest text-white">
          Page not found
        </h1>
        <p className="mt-2 text-xs leading-relaxed text-zinc-500">
          This route is not part of the Assest workspace console.
        </p>
        <Link
          href="/"
          className="mt-5 inline-flex items-center gap-2 rounded-lg border border-white/10 bg-white px-3 py-2 text-[10px] font-black uppercase tracking-widest text-black transition-colors hover:bg-primary"
        >
          <Home className="h-3.5 w-3.5" />
          Home
        </Link>
      </div>
    </div>
  );
}

