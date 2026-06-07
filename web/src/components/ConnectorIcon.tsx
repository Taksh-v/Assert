import React from "react";

interface ConnectorIconProps {
  type: string;
  className?: string;
}

export default function ConnectorIcon({ type, className = "h-5 w-5" }: ConnectorIconProps) {
  const normalized = type.toLowerCase().replace("-", "_");

  switch (normalized) {
    case "notion":
      return (
        <svg viewBox="0 0 24 24" className={className} fill="currentColor">
          <path d="M4.46 2h15.08c1.35 0 2.46 1.1 2.46 2.46v15.08c0 1.35-1.1 2.46-2.46 2.46H4.46A2.46 2.46 0 012 19.54V4.46C2 3.1 3.1 2 4.46 2zM15.42 6.55h-2.12v1.07h.76v7.35l-2.61-7.85c-.09-.27-.27-.47-.56-.47H8.81L5.94 15.6v-8l1-.47V6.08H4.62v1.07h.71V17h2.24l3.15-9.15v8h-.76v1.07H13.6v-1.07h-.76v-7.9l2.76 8.3c.09.28.32.48.61.48H18.5V17h.76V6.55h-3.84z" />
        </svg>
      );

    case "google_drive":
      return (
        <svg viewBox="0 0 24 24" className={className} fill="none">
          <path d="M14.6 2h-5.2L2 12h5.2L14.6 2z" fill="#FFC107" />
          <path d="M22 12H8.3l6.5 10H22l-6.5-10z" fill="#4CAF50" />
          <path d="M8.3 12L2 2h13l-6.7 10z" fill="#1E88E5" />
        </svg>
      );

    case "slack":
      return (
        <svg viewBox="0 0 24 24" className={className} fill="none">
          <path d="M5.04 15.17a2.53 2.53 0 1 1-2.52 2.52h2.52v-2.52zM6.3 15.17a2.53 2.53 0 0 1 2.52-2.52h5.04a2.53 2.53 0 0 1 2.52 2.52v5.04a2.53 2.53 0 0 1-2.52 2.52H8.82a2.53 2.53 0 0 1-2.52-2.52v-5.04z" fill="#36C5F0" />
          <path d="M8.82 5.04a2.53 2.53 0 1 1-2.52-2.52v2.52h2.52zM8.82 6.3a2.53 2.53 0 0 1 2.52 2.52v5.04a2.53 2.53 0 0 1-2.52 2.52H3.78a2.53 2.53 0 0 1-2.52-2.52V8.82a2.53 2.53 0 0 1 2.52-2.52h5.04z" fill="#2EB67D" />
          <path d="M18.96 8.82a2.53 2.53 0 1 1 2.52-2.52h-2.52v2.52zM17.7 8.82a2.53 2.53 0 0 1-2.52 2.52h-5.04a2.53 2.53 0 0 1-2.52-2.52V3.78a2.53 2.53 0 0 1 2.52-2.52h5.04a2.53 2.53 0 0 1 2.52 2.52v5.04z" fill="#ECB22E" />
          <path d="M15.18 18.96a2.53 2.53 0 1 1 2.52 2.52h-2.52v-2.52zM15.18 17.7a2.53 2.53 0 0 1-2.52-2.52v-5.04a2.53 2.53 0 0 1 2.52-2.52h5.04a2.53 2.53 0 0 1 2.52 2.52v5.04a2.53 2.53 0 0 1-2.52 2.52h-5.04z" fill="#E01E5A" />
        </svg>
      );

    case "github":
      return (
        <svg viewBox="0 0 24 24" className={className} fill="currentColor">
          <path fillRule="evenodd" clipRule="evenodd" d="M12 2C6.48 2 2 6.48 2 12c0 4.42 2.87 8.17 6.84 9.5.5.08.66-.23.66-.5v-1.69c-2.77.6-3.36-1.34-3.36-1.34-.46-1.16-1.11-1.47-1.11-1.47-.9-.62.07-.6.07-.6 1 .07 1.53 1.03 1.53 1.03.87 1.52 2.34 1.07 2.91.83.09-.65.35-1.09.63-1.34-2.22-.25-4.55-1.11-4.55-4.92 0-1.11.38-2 1.03-2.71-.1-.25-.45-1.29.1-2.64 0 0 .84-.27 2.75 1.02.79-.22 1.65-.33 2.5-.33.85 0 1.71.11 2.5.33 1.91-1.29 2.75-1.02 2.75-1.02.55 1.35.2 2.39.1 2.64.65.71 1.03 1.6 1.03 2.71 0 3.82-2.34 4.66-4.57 4.91.36.31.69.92.69 1.85V21c0 .27.16.59.67.5C19.14 20.16 22 16.42 22 12A10 10 0 0 0 12 2z" />
        </svg>
      );

    default:
      return (
        <svg viewBox="0 0 24 24" className={className} fill="none" stroke="currentColor" strokeWidth="2">
          <circle cx="12" cy="12" r="10" />
          <path d="M12 16v-4" />
          <path d="M12 8h.01" />
        </svg>
      );
  }
}
