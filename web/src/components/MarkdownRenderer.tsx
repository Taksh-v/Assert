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
    <div className="prose prose-invert max-w-none text-sm leading-relaxed text-[var(--text-secondary)] font-normal">
      <ReactMarkdown
        remarkPlugins={[remarkGfm]}
        components={{
          // Headings
          h1: ({ children }) => (
            <h1 className="text-base font-bold text-[var(--text-primary)] mt-6 mb-3 border-b border-[var(--border-subtle)] pb-2">
              {children}
            </h1>
          ),
          h2: ({ children }) => (
            <h2 className="text-sm font-bold text-[var(--text-primary)] mt-5 mb-2">
              {children}
            </h2>
          ),
          h3: ({ children }) => (
            <h3 className="text-sm font-medium text-[var(--text-primary)] mt-4 mb-1.5">
              {children}
            </h3>
          ),
          // Paragraphs with citation support
          p: ({ children }) => (
            <p className="text-sm leading-relaxed text-[var(--text-secondary)] mb-3">
              {renderWithCitations(children, citations, onCitationClick)}
            </p>
          ),
          // Lists
          ul: ({ children }) => (
            <ul className="list-none space-y-2 mb-4 pl-0">{children}</ul>
          ),
          ol: ({ children }) => (
            <ol className="list-decimal list-inside space-y-2 mb-4 pl-0 text-[var(--text-secondary)]">
              {children}
            </ol>
          ),
          li: ({ children }) => (
            <li className="text-sm leading-relaxed text-[var(--text-secondary)] flex items-start gap-2.5">
              <span className="w-1.5 h-1.5 rounded-full bg-[var(--accent)] mt-2.5 shrink-0" />
              <span>{renderWithCitations(children, citations, onCitationClick)}</span>
            </li>
          ),
          // Code blocks
          code: ({ className, children, ...props }) => {
            const isInline = !className;
            if (isInline) {
              return (
                <code className="bg-[var(--accent-muted)] text-[var(--accent)] px-1.5 py-0.5 rounded text-xs font-mono">
                  {children}
                </code>
              );
            }
            return (
              <code
                className="block bg-[var(--bg-root)] border border-[var(--border-subtle)] rounded-xl p-4 text-xs font-mono text-[var(--text-secondary)] overflow-x-auto my-3"
                {...props}
              >
                {children}
              </code>
            );
          },
          pre: ({ children }) => <pre className="my-0">{children}</pre>,
          // Tables
          table: ({ children }) => (
            <div className="overflow-x-auto my-4 rounded-xl border border-[var(--border-subtle)] bg-[var(--bg-surface)] shadow-sm">
              <table className="w-full text-xs">{children}</table>
            </div>
          ),
          thead: ({ children }) => (
            <thead className="bg-white/[0.7] border-b border-[var(--border-subtle)]">
              {children}
            </thead>
          ),
          th: ({ children }) => (
            <th className="px-4 py-2.5 text-left font-semibold text-[var(--text-primary)] text-xs">
              {children}
            </th>
          ),
          td: ({ children }) => (
            <td className="px-4 py-2.5 text-[var(--text-secondary)] border-t border-[var(--border-subtle)]">
              {children}
            </td>
          ),
          // Blockquotes
          blockquote: ({ children }) => (
            <blockquote className="border-l-2 border-[var(--accent)]/40 pl-3 my-4 text-[var(--text-muted)] italic text-xs">
              {children}
            </blockquote>
          ),
          // Strong/Bold
          strong: ({ children }) => (
            <strong className="font-semibold text-[var(--text-primary)]">{children}</strong>
          ),
          // Links
          a: ({ href, children }) => (
            <a
              href={href}
              target="_blank"
              rel="noopener noreferrer"
              className="text-[var(--accent)] hover:text-[var(--accent-hover)] underline underline-offset-2 transition-colors"
            >
              {children}
            </a>
          ),
          // Horizontal rules
          hr: () => <hr className="border-[var(--border-subtle)] my-5" />,
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
          className="inline-flex items-center justify-center min-w-[18px] h-[18px] px-1.5 mx-0.5 rounded bg-[var(--accent-muted)] border border-[var(--accent)]/20 text-[var(--accent)] text-xs font-bold hover:bg-[var(--accent)]/20 hover:border-[var(--accent)]/40 transition-all cursor-pointer align-baseline"
        >
          {citationId}
        </button>
      );
    });
  });
}
