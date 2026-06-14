
import { Menu, Search, Plus } from 'lucide-react';

export function TopBar() {
  return (
    <div className="flex items-center justify-between p-4 border-b border-jarvis-border">
      <button>
        <Menu className="h-6 w-6 text-jarvis-muted" />
      </button>
      <div className="flex-1 flex justify-center">
        {/* Model Selector Here */}
      </div>
      <div className="flex items-center gap-4">
        <button>
          <Search className="h-6 w-6 text-jarvis-muted" />
        </button>
        <button>
          <Plus className="h-6 w-6 text-jarvis-muted" />
        </button>
      </div>
    </div>
  );
}
