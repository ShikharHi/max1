
import { AgentStepBlock } from './AgentStepBlock';
// import { AgentStep } from '@/types';

interface AgentStepListProps {
  steps: any[]; // TODO: Replace with real AgentStep[] type
}

export function AgentStepList({ steps }: AgentStepListProps) {
  return (
    <div className="flex flex-col space-y-2">
      {steps.map(step => (
        <AgentStepBlock key={step.id} step={step} />
      ))}
    </div>
  );
}
