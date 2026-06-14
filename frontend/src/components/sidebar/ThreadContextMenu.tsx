
'use client';

import { Star, Edit, Trash2 } from 'lucide-react';

interface ThreadContextMenuProps {
  isOpen: boolean;
  onClose: () => void;
  position: { x: number; y: number };
  threadId: string;
}

export function ThreadContextMenu({ isOpen, onClose, position, threadId }: ThreadContextMenuProps) {
  if (!isOpen) return null;

  return (
    <div
      className="fixed z-10 bg-jarvis-surface border border-jarvis-border rounded-md shadow-lg"
      style={{ top: position.y, left: position.x }}
      onClick={onClose}
    >
      <ul className="py-1">
        <li className="px-4 py-2 hover:bg-jarvis-input flex items-center gap-2 cursor-pointer">
          <Star className="h-4 w-4" />
          <span>Star</span>
        </li>
        <li className="px-4 py-2 hover:bg-jarvis-input flex items-center gap-2 cursor-pointer">
          <Edit className="h-4 w-4" />
          <span>Rename</span>
        </li>
        <li className="px-4 py-2 hover:bg-jarvis-input flex items-center gap-2 text-red-500 cursor-pointer">
          <Trash2 className="h-4 w-4" />
          <span>Delete</span>
        </li>
      </ul>
    </div>
  );
}
