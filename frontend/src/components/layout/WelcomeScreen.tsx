
import { Code, Bot, BrainCircuit, Pen, Book } from 'lucide-react';

const quickActions = [
  { icon: Code, text: 'Code' },
  { icon: Bot, text: 'Strategize' },
  { icon: BrainCircuit, text: 'Create' },
  { icon: Pen, text: 'Write' },
  { icon: Book, text: 'Learn' },
];

function getGreeting() {
    const now = new Date();
    const hours = now.getHours();

    if (hours < 12) {
        return 'Good morning, sir.';
    } else if (hours < 18) {
        return 'Good afternoon, sir.';
    } else {
        return 'Good evening, sir.';
    }
}

export function WelcomeScreen() {
  return (
    <div className="flex flex-col items-center justify-center h-full bg-jarvis-bg text-jarvis-text">
      <div className="text-center">
        <div className="text-jarvis-cyan text-5xl mb-4">*</div>
        <h1 className="text-4xl font-semibold mb-12">{getGreeting()}</h1>
      </div>
      <div className="w-full max-w-2xl px-4">
        {/* <ChatInput /> will be placed here by the parent layout */}
      </div>
      <div className="mt-8 flex gap-4">
        {quickActions.map(({ icon: Icon, text }) => (
          <button key={text} className="flex items-center gap-2 px-4 py-2 bg-jarvis-surface rounded-lg hover:bg-jarvis-input transition-colors">
            <Icon className="w-5 h-5 text-jarvis-muted" />
            <span className="text-sm font-medium">{text}</span>
          </button>
        ))}
      </div>
    </div>
  );
}
