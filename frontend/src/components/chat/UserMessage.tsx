
import { ThumbsUp, ThumbsDown, RefreshCw } from 'lucide-react';

interface UserMessageProps {
  content: string;
}

export function UserMessage({ content }: UserMessageProps) {
  return (
    <div className="flex justify-end">
      <div className="bg-[#1e1e28] rounded-2xl p-4 max-w-xl text-jarvis-text">
        <p>{content}</p>
        <div className="flex justify-end items-center mt-2 text-xs text-jarvis-muted">
          <span>8:31 PM</span>
        </div>
      </div>
    </div>
  );
}
