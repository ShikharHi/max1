
'use client';

import { useEffect, useRef } from 'react';

// Dummy messages for layout purposes
const dummyMessages = [
  { id: '1', role: 'human', content: 'Hello, JARVIS.' },
  { id: '2', role: 'assistant', content: 'Good evening, sir. How may I assist you today?' },
  { id: '3', role: 'human', content: 'I need you to build the frontend for our new AI assistant platform.' },
  {
    id: '4',
    role: 'assistant',
    content: 'Of course. I will begin by scaffolding the project structure and installing the necessary dependencies. I will then proceed to build the individual components as per the design specification.',
    agentSteps: [
      { id: 's1', type: 'agent_action', label: 'Checking available skills', status: 'done' },
      { id: 's2', type: 'tool_call', label: 'Create project structure', status: 'done' },
    ]
  },
];

export function MessageList() {
  const scrollRef = useRef<HTMLDivElement>(null);

  useEffect(() => {
    if (scrollRef.current) {
      scrollRef.current.scrollTop = scrollRef.current.scrollHeight;
    }
  }, []);

  return (
    <div ref={scrollRef} className="flex-1 overflow-y-auto p-6 space-y-8">
      {/* This will be replaced with dynamic messages from the store */}
    </div>
  );
}
