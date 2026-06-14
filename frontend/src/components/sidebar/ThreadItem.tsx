
'use client';

import { MoreHorizontal } from 'lucide-react';
import { useState } from 'react';
import { ThreadContextMenu } from './ThreadContextMenu';

export function ThreadItem({ thread }: { thread: any }) {
  const [menuOpen, setMenuOpen] = useState(false);
  const [menuPosition, setMenuPosition] = useState({ x: 0, y: 0 });

  const handleContextMenu = (e: React.MouseEvent) => {
    e.preventDefault();
    setMenuPosition({ x: e.clientX, y: e.clientY });
    setMenuOpen(true);
  };

  return (
    <div
      className={`group relative rounded-md p-2 cursor-pointer ${thread.active ? 'bg-jarvis-input' : 'hover:bg-jarvis-input'}`}
      onContextMenu={handleContextMenu}
    >
      {thread.active && <div className="absolute left-0 top-0 h-full w-1 bg-jarvis-cyan rounded-r-full"></div>}
      <p className="text-sm truncate">{thread.title}</p>
      <button className="absolute right-2 top-1/2 -translate-y-1/2 opacity-0 group-hover:opacity-100">
        <MoreHorizontal className="h-5 w-5 text-jarvis-muted" />
      </button>
      <ThreadContextMenu
        isOpen={menuOpen}
        onClose={() => setMenuOpen(false)}
        position={menuPosition}
        threadId={thread.id}
      />
    </div>
  );
}
