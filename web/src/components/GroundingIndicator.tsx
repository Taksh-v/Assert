"use client";

import { Activity, Shield, ShieldAlert, ShieldCheck, Zap, Brain, Wrench } from "lucide-react";

interface GroundingIndicatorProps {
  groundingScore: number;
  tier: string;
  citationCount: number;
}

/**
 * Visual indicator showing response quality metrics:
 * - Response tier badge (Quick / Standard / Deep)
 * - Grounding confidence score
 * - Number of sources cited
 */
export default function GroundingIndicator({
  groundingScore,
  tier,
  citationCount,
}: GroundingIndicatorProps) {
  const tierConfig = getTierConfig(tier);
  const groundingConfig = getGroundingConfig(groundingScore);

  return (
    <div className="flex items-center gap-2 flex-wrap mt-1">
      {/* Response Tier Badge */}
      <div
        className={`flex items-center gap-1.5 px-2 py-0.5 rounded-full border text-[11px] font-semibold tracking-wide ${tierConfig.classes}`}
      >
        <tierConfig.icon className="h-3 w-3" />
        <span>{tierConfig.label}</span>
      </div>

      {/* Grounding Score */}
      <div
        className={`flex items-center gap-1.5 px-2 py-0.5 rounded-full border text-[11px] font-semibold tracking-wide ${groundingConfig.classes}`}
      >
        <groundingConfig.icon className="h-3 w-3" />
        <span>{Math.round(groundingScore * 100)}% Grounded</span>
      </div>

      {/* Citation Count */}
      {citationCount > 0 && (
        <div className="flex items-center gap-1 px-2 py-0.5 rounded-full border border-[var(--border-subtle)] bg-[var(--bg-surface)] text-[11px] font-medium text-[var(--text-secondary)]">
          <span>{citationCount} source{citationCount !== 1 ? "s" : ""} cited</span>
        </div>
      )}
    </div>
  );
}

function getTierConfig(tier: string) {
  switch (tier) {
    case "direct":
      return {
        label: "Quick",
        icon: Zap,
        classes: "border-[var(--success-muted)] bg-[var(--success-muted)] text-[var(--success)]",
      };
    case "fast_rag":
      return {
        label: "Standard",
        icon: Activity,
        classes: "border-[var(--accent-muted)] bg-[var(--accent-muted)] text-[var(--accent)]",
      };
    case "full_swarm":
      return {
        label: "Deep Analysis",
        icon: Brain,
        classes: "border-indigo-500/20 bg-indigo-500/5 text-indigo-400",
      };
    case "tool_exec":
      return {
        label: "Tool Exec",
        icon: Wrench,
        classes: "border-[var(--warning-muted)] bg-[var(--warning-muted)] text-[var(--warning)]",
      };
    default:
      return {
        label: "Standard",
        icon: Activity,
        classes: "border-[var(--border-subtle)] bg-white/[0.02] text-[var(--text-secondary)]",
      };
  }
}

function getGroundingConfig(score: number) {
  if (score >= 0.7) {
    return {
      icon: ShieldCheck,
      classes: "border-[var(--success-muted)] bg-[var(--success-muted)] text-[var(--success)]",
    };
  }
  if (score >= 0.4) {
    return {
      icon: Shield,
      classes: "border-[var(--warning-muted)] bg-[var(--warning-muted)] text-[var(--warning)]",
    };
  }
  return {
    icon: ShieldAlert,
    classes: "border-[var(--danger-muted)] bg-[var(--danger-muted)] text-[var(--danger)]",
  };
}
