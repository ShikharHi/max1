
import { AgentStepList } from './AgentStepList';
import { MessageActions } from './MessageActions';
// import { AgentStep } from '@/types';

interface AssistantMessageProps {
  content: string;
  agentSteps?: any[]; // TODO: Replace with real AgentStep[] type
}

export function AssistantMessage({ content, agentSteps }: AssistantMessageProps) {
  return (
    <div className="flex flex-col space-y-4">
      {agentSteps && <AgentStepList steps={agentSteps} />}
      <div className="prose prose-invert max-w-none text-jarvis-text">
        {content}
      </div>
      <MessageActions />
    </div>
  );
}
