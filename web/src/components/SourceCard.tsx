import React from 'react';
import { Source } from '../lib/api';

interface SourceCardProps {
  source: Source;
  index: number;
}

export function SourceCard({ source, index }: SourceCardProps) {
  return (
    <a 
      href={source.url}
      target="_blank"
      rel="noopener noreferrer"
      className="inline-flex items-center px-3 py-1.5 mr-2 mb-2 text-sm font-medium text-gray-700 bg-gray-100 rounded-lg hover:bg-gray-200 transition-colors border border-gray-200"
    >
      <span className="w-5 h-5 flex items-center justify-center bg-white rounded-full text-xs font-bold text-gray-500 mr-2 shadow-sm">
        {index + 1}
      </span>
      <span className="truncate max-w-[150px]">{source.title}</span>
      <svg className="w-3 h-3 ml-2 text-gray-400" fill="none" stroke="currentColor" viewBox="0 0 24 24">
        <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M10 6H6a2 2 0 00-2 2v10a2 2 0 002 2h10a2 2 0 002-2v-4M14 4h6m0 0v6m0-6L10 14" />
      </svg>
    </a>
  );
}
