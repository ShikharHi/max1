
'use client';

import { useState } from 'react';
import { Plus, Mic, Send } from 'lucide-react';

export function ChatInput() {
  const [input, setInput] = useState('');

  return (
    <div className="relative">
      <div className="absolute inset-y-0 left-0 flex items-center pl-4">
        <button className="p-2 bg-jarvis-cyan rounded-full text-jarvis-bg">
          <Plus className="h-5 w-5" />
        </button>
      </div>
      <input
        type="text"
        value={input}
        onChange={(e) => setInput(e.target.value)}
        placeholder="Paste a doc, an email, or a question to get started"
        className="w-full bg-jarvis-input border border-jarvis-border rounded-full py-4 pl-14 pr-24 text-jarvis-text placeholder-jarvis-muted focus:outline-none focus:ring-2 focus:ring-jarvis-cyan"
      />
      <div className="absolute inset-y-0 right-0 flex items-center pr-4 gap-2">
        <button className="p-2 text-jarvis-muted hover:text-jarvis-text">
          <Mic className="h-5 w-5" />
        </button>
        <button
          className={`p-2 rounded-full ${input ? 'bg-jarvis-violet text-white' : 'bg-jarvis-surface text-jarvis-muted'}`}
          disabled={!input}
        >
          <Send className="h-5 w-5" />
        </button>
      </div>
    </div>
  );
}
