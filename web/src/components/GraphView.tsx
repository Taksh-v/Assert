"use client";

import React from 'react';

export const GraphView = () => {
  return (
    <div className="glass-card p-8 h-[400px] flex flex-col relative overflow-hidden">
      <div className="flex justify-between items-center mb-6">
        <h3 className="text-xl font-bold text-[var(--text-primary)]">Knowledge Graph</h3>
        <span className="text-[10px] font-black uppercase text-blue-400 bg-blue-500/10 px-3 py-1 rounded-full">Memgraph Live</span>
      </div>
      
      {/* Mock SVG Graph */}
      <div className="flex-1 flex items-center justify-center">
        <svg width="100%" height="100%" viewBox="0 0 400 300">
          {/* Relationships */}
          <line x1="200" y1="150" x2="100" y2="80" stroke="#3b82f6" strokeWidth="2" strokeOpacity="0.3" />
          <line x1="200" y1="150" x2="300" y2="80" stroke="#3b82f6" strokeWidth="2" strokeOpacity="0.3" />
          <line x1="200" y1="150" x2="200" y2="250" stroke="#3b82f6" strokeWidth="2" strokeOpacity="0.3" />
          
          {/* Nodes */}
          <circle cx="200" cy="150" r="12" fill="#3b82f6" className="animate-pulse" />
          <text x="200" y="130" textAnchor="middle" fill="var(--text-primary)" fontSize="10" fontWeight="bold">Project Assest</text>
          
          <circle cx="100" cy="80" r="8" fill="#10b981" />
          <text x="100" y="65" textAnchor="middle" fill="#9ca3af" fontSize="8">Notion Page</text>
          
          <circle cx="300" cy="80" r="8" fill="#f59e0b" />
          <text x="300" y="65" textAnchor="middle" fill="#9ca3af" fontSize="8">Slack Thread</text>
          
          <circle cx="200" cy="250" r="8" fill="#ec4899" />
          <text x="200" y="270" textAnchor="middle" fill="#9ca3af" fontSize="8">Owner: Taksh</text>
        </svg>
      </div>
      
      <div className="absolute bottom-4 left-8 text-[10px] text-zinc-500 font-medium">
        Showing 14 entities and 32 relationships
      </div>
    </div>
  );
};
