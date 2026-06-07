import Link from "next/link";
import { Home } from "lucide-react";

export default function NotFound() {
  return (
    <div className="flex h-full min-h-[420px] items-center justify-center bg-[var(--bg-root)] px-6 text-[var(--text-primary)] animate-fade-in">
      <div className="w-full max-w-sm rounded-xl border border-[var(--border-subtle)] bg-[var(--bg-surface)] p-6 text-center shadow-[var(--shadow-card)]">
        <h1 className="text-sm font-bold text-white">
          Page Not Found
        </h1>
        <p className="mt-2 text-xs leading-relaxed text-[var(--text-secondary)]">
          This route is not part of the Assest workspace console.
        </p>
        <Link
          href="/"
          className="mt-5 inline-flex items-center gap-1.5 rounded-xl bg-[var(--accent)] hover:bg-[var(--accent-hover)] text-white px-4 py-2 text-xs font-semibold transition-colors shadow-sm cursor-pointer"
        >
          <Home className="h-4 w-4" />
          <span>Home</span>
        </Link>
      </div>
    </div>
  );
}
