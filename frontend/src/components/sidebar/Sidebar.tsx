
import { ThreadList } from './ThreadList';
import { ChevronLeft, Plus } from 'lucide-react';

export function Sidebar() {
  return (
    <div className="w-[280px] bg-jarvis-surface flex flex-col h-full text-jarvis-text">
      <div className="p-4">
        <h1 className="text-2xl font-bold text-jarvis-cyan">JARVIS</h1>
      </div>
      <div className="p-4">
        <button className="w-full flex items-center justify-center gap-2 bg-jarvis-violet text-white rounded-md py-2">
          <Plus className="h-5 w-5" />
          <span>New chat</span>
        </button>
      </div>
      <div className="flex-1 overflow-y-auto">
        <ThreadList />
      </div>
      <div className="p-4 border-t border-jarvis-border">
        <div className="flex items-center justify-between">
          <div className="flex items-center gap-2">
            <div className="h-8 w-8 rounded-full bg-jarvis-cyan"></div>
            <span>User</span>
          </div>
          <button>
            <ChevronLeft className="h-5 w-5 text-jarvis-muted" />
          </button>
        </div>
      </div>
    </div>
  );
}
