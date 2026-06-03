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
    <div className="flex items-center gap-2 flex-wrap">
      {/* Response Tier Badge */}
      <div
        className={`flex items-center gap-1.5 px-2.5 py-1 rounded-lg border text-[9px] font-black uppercase tracking-widest ${tierConfig.classes}`}
      >
        <tierConfig.icon className="h-3 w-3" />
        {tierConfig.label}
      </div>

      {/* Grounding Score */}
      <div
        className={`flex items-center gap-1.5 px-2.5 py-1 rounded-lg border text-[9px] font-black uppercase tracking-widest ${groundingConfig.classes}`}
      >
        <groundingConfig.icon className="h-3 w-3" />
        {Math.round(groundingScore * 100)}% Grounded
      </div>

      {/* Citation Count */}
      {citationCount > 0 && (
        <div className="flex items-center gap-1 px-2 py-1 rounded-lg border border-white/[0.06] bg-white/[0.02] text-[9px] font-bold text-zinc-400">
          {citationCount} source{citationCount !== 1 ? "s" : ""}
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
        classes: "border-emerald-500/20 bg-emerald-500/5 text-emerald-400",
      };
    case "fast_rag":
      return {
        label: "Standard",
        icon: Activity,
        classes: "border-primary/20 bg-primary/5 text-primary",
      };
    case "full_swarm":
      return {
        label: "Deep Analysis",
        icon: Brain,
        classes: "border-purple-500/20 bg-purple-500/5 text-purple-400",
      };
    case "tool_exec":
      return {
        label: "Tool Exec",
        icon: Wrench,
        classes: "border-amber-500/20 bg-amber-500/5 text-amber-400",
      };
    default:
      return {
        label: "Standard",
        icon: Activity,
        classes: "border-white/[0.06] bg-white/[0.02] text-zinc-400",
      };
  }
}

function getGroundingConfig(score: number) {
  if (score >= 0.7) {
    return {
      icon: ShieldCheck,
      classes: "border-emerald-500/20 bg-emerald-500/5 text-emerald-400",
    };
  }
  if (score >= 0.4) {
    return {
      icon: Shield,
      classes: "border-amber-500/20 bg-amber-500/5 text-amber-400",
    };
  }
  return {
    icon: ShieldAlert,
    classes: "border-red-500/20 bg-red-500/5 text-red-400",
  };
}
