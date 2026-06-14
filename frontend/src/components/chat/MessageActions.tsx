
import { Copy, ThumbsUp, ThumbsDown, RefreshCw } from 'lucide-react';

export function MessageActions() {
  return (
    <div className="flex items-center gap-2 text-jarvis-muted">
      <button className="p-1 hover:text-jarvis-text">
        <Copy className="h-4 w-4" />
      </button>
      <button className="p-1 hover:text-jarvis-text">
        <ThumbsUp className="h-4 w-4" />
      </button>
      <button className="p-1 hover:text-jarvis-text">
        <ThumbsDown className="h-4 w-4" />
      </button>
      <button className="p-1 hover:text-jarvis-text">
        <RefreshCw className="h-4 w-4" />
      </button>
    </div>
  );
}
