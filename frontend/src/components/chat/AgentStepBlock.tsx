
'use client';

import { useState } from 'react';
import { ChevronRight, CheckCircle, AlertCircle, Loader } from 'lucide-react';
// import { AgentStep } from '@/types';

const statusIcons = {
  running: <Loader className="h-4 w-4 animate-spin text-jarvis-cyan" />,
  done: <CheckCircle className="h-4 w-4 text-green-500" />,
  error: <AlertCircle className="h-4 w-4 text-red-500" />,
};

export function AgentStepBlock({ step }: { step: any }) { // TODO: Replace with real AgentStep type
  const [isExpanded, setIsExpanded] = useState(false);

  return (
    <div className="border border-jarvis-border rounded-lg bg-jarvis-surface overflow-hidden">
      <button
        className="w-full flex items-center justify-between p-3 text-left"
        onClick={() => setIsExpanded(!isExpanded)}
      >
        <div className="flex items-center gap-3">
          {statusIcons[step.status as keyof typeof statusIcons]}
          <span className="font-mono text-sm text-jarvis-text">{step.label}</span>
        </div>
        <ChevronRight
          className={`h-5 w-5 text-jarvis-muted transform transition-transform ${isExpanded ? 'rotate-90' : ''}`}
        />
      </button>
      {isExpanded && (
        <div className="p-4 border-t border-jarvis-border bg-jarvis-bg">
          <pre className="text-xs text-jarvis-muted whitespace-pre-wrap">
            {JSON.stringify({ input: step.input, output: step.output }, null, 2)}
          </pre>
        </div>
      )}
    </div>
  );
}
