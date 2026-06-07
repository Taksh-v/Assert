import React from "react";
import { ExternalLink } from "lucide-react";

interface SourceCardProps {
  source: {
    title: string;
    url: string;
  };
  index: number;
}

export function SourceCard({ source, index }: SourceCardProps) {
  return (
    <a 
      href={source.url}
      target="_blank"
      rel="noopener noreferrer"
      className="inline-flex items-center px-3 py-1.5 rounded-xl text-xs font-semibold text-[var(--text-secondary)] bg-[var(--bg-surface)] hover:bg-[var(--bg-surface-hover)] hover:text-[var(--text-primary)] transition-all border border-[var(--border-subtle)] hover:border-zinc-800 shadow-sm"
    >
      <span className="w-4 h-4 flex items-center justify-center bg-[var(--bg-root)] border border-[var(--border-subtle)] rounded-full text-[10px] font-bold text-[var(--accent)] mr-2 shrink-0">
        {index + 1}
      </span>
      <span className="truncate max-w-[150px]">{source.title}</span>
      <ExternalLink className="w-3 h-3 ml-2 text-[var(--text-muted)] shrink-0" />
    </a>
  );
}
