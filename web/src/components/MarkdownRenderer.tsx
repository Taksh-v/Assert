"use client";

import React from "react";
import ReactMarkdown from "react-markdown";
import remarkGfm from "remark-gfm";

interface CitationSource {
  id: number;
  title: string;
  url: string;
  section_heading?: string;
  confidence?: number;
  verified?: boolean;
}

interface MarkdownRendererProps {
  content: string;
  citations?: CitationSource[];
  onCitationClick?: (id: number) => void;
}

/**
 * Rich Markdown renderer for LLM responses.
 * Transforms [N] citation patterns into interactive badges.
 */
export default function MarkdownRenderer({
  content,
  citations = [],
  onCitationClick,
}: MarkdownRendererProps) {
  return (
    <div className="prose prose-invert max-w-none text-xs leading-6 text-zinc-300 font-medium">
      <ReactMarkdown
        remarkPlugins={[remarkGfm]}
        components={{
          // Headings
          h1: ({ children }) => (
            <h1 className="text-sm font-black text-white mt-5 mb-2 uppercase tracking-wider border-b border-white/[0.06] pb-2">
              {children}
            </h1>
          ),
          h2: ({ children }) => (
            <h2 className="text-[11px] font-black text-white mt-4 mb-1.5 uppercase tracking-wider">
              {children}
            </h2>
          ),
          h3: ({ children }) => (
            <h3 className="text-[11px] font-bold text-zinc-200 mt-3 mb-1">
              {children}
            </h3>
          ),
          // Paragraphs with citation support
          p: ({ children }) => (
            <p className="text-xs leading-6 text-zinc-300 mb-2.5">
              {renderWithCitations(children, citations, onCitationClick)}
            </p>
          ),
          // Lists
          ul: ({ children }) => (
            <ul className="list-none space-y-1.5 mb-3 pl-0">{children}</ul>
          ),
          ol: ({ children }) => (
            <ol className="list-decimal list-inside space-y-1.5 mb-3 pl-0 text-zinc-300">
              {children}
            </ol>
          ),
          li: ({ children }) => (
            <li className="text-xs leading-5 text-zinc-300 flex items-start gap-2">
              <span className="w-1 h-1 rounded-full bg-primary mt-2 shrink-0" />
              <span>{renderWithCitations(children, citations, onCitationClick)}</span>
            </li>
          ),
          // Code blocks
          code: ({ className, children, ...props }) => {
            const isInline = !className;
            if (isInline) {
              return (
                <code className="bg-white/[0.06] text-primary px-1.5 py-0.5 rounded text-[10px] font-mono">
                  {children}
                </code>
              );
            }
            return (
              <code
                className="block bg-[#0a0f1a] border border-white/[0.04] rounded-xl p-4 text-[10px] font-mono text-zinc-300 overflow-x-auto my-3"
                {...props}
              >
                {children}
              </code>
            );
          },
          pre: ({ children }) => <pre className="my-0">{children}</pre>,
          // Tables
          table: ({ children }) => (
            <div className="overflow-x-auto my-3 rounded-xl border border-white/[0.04]">
              <table className="w-full text-[10px]">{children}</table>
            </div>
          ),
          thead: ({ children }) => (
            <thead className="bg-white/[0.03] border-b border-white/[0.04]">
              {children}
            </thead>
          ),
          th: ({ children }) => (
            <th className="px-3 py-2 text-left font-black text-zinc-400 uppercase tracking-wider text-[9px]">
              {children}
            </th>
          ),
          td: ({ children }) => (
            <td className="px-3 py-2 text-zinc-300 border-t border-white/[0.03]">
              {children}
            </td>
          ),
          // Blockquotes (for disclaimers)
          blockquote: ({ children }) => (
            <blockquote className="border-l-2 border-primary/40 pl-3 my-3 text-zinc-400 italic text-[10px]">
              {children}
            </blockquote>
          ),
          // Strong/Bold
          strong: ({ children }) => (
            <strong className="font-bold text-white">{children}</strong>
          ),
          // Links
          a: ({ href, children }) => (
            <a
              href={href}
              target="_blank"
              rel="noopener noreferrer"
              className="text-primary hover:text-primary/80 underline underline-offset-2 transition-colors"
            >
              {children}
            </a>
          ),
          // Horizontal rules
          hr: () => <hr className="border-white/[0.06] my-4" />,
        }}
      >
        {content}
      </ReactMarkdown>
    </div>
  );
}

/**
 * Process children to replace [N] patterns with clickable citation badges.
 */
function renderWithCitations(
  children: React.ReactNode,
  citations: CitationSource[],
  onCitationClick?: (id: number) => void
): React.ReactNode {
  if (!children) return children;

  return React.Children.map(children, (child) => {
    if (typeof child !== "string") return child;

    // Split on citation pattern [N]
    const parts = child.split(/(\[\d+\])/g);
    if (parts.length === 1) return child;

    return parts.map((part, i) => {
      const match = part.match(/^\[(\d+)\]$/);
      if (!match) return part;

      const citationId = parseInt(match[1]);
      const source = citations.find((c) => c.id === citationId);
      const title = source?.title || `Source ${citationId}`;
      const section = source?.section_heading
        ? ` — ${source.section_heading}`
        : "";

      return (
        <button
          key={`cite-${i}-${citationId}`}
          onClick={() => onCitationClick?.(citationId)}
          title={`${title}${section}`}
          className="inline-flex items-center justify-center min-w-[18px] h-[18px] px-1 mx-0.5 rounded bg-primary/10 border border-primary/20 text-primary text-[9px] font-black hover:bg-primary/20 hover:border-primary/40 transition-all cursor-pointer align-baseline"
        >
          {citationId}
        </button>
      );
    });
  });
}
