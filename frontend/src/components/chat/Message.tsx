
import { UserMessage } from './UserMessage';
import { AssistantMessage } from './AssistantMessage';
// import { Message as MessageType } from '@/types';

// TODO: Replace with real MessageType
export function Message({ message }: { message: any }) { 
  if (message.role === 'human') {
    return <UserMessage content={message.content} />;
  }
  return <AssistantMessage content={message.content} agentSteps={message.agentSteps} />;
}
