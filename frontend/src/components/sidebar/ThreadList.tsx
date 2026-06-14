
import { ThreadItem } from './ThreadItem';

const dummyThreads = [
  { id: '1', title: 'Frontend implementation for JARVIS', active: true },
  { id: '2', title: 'LangGraph backend integration' },
  { id: '3', title: 'Zustand state management strategy' },
];

export function ThreadList() {
  return (
    <div className="p-4 space-y-2">
      <h2 className="text-xs font-semibold text-jarvis-muted uppercase tracking-wider">Recents</h2>
      {dummyThreads.map(thread => (
        <ThreadItem key={thread.id} thread={thread} />
      ))}
    </div>
  );
}
