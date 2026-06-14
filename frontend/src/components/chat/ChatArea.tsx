
import { MessageList } from "./MessageList";
import { ChatInput } from "../input/ChatInput";

export function ChatArea() {
  return (
    <div className="flex flex-col h-full bg-jarvis-bg">
      <MessageList />
      <div className="px-4 pb-4">
        <ChatInput />
        <p className="text-xs text-center text-jarvis-muted mt-2">
          Claude is AI and can make mistakes. Please check important information.
        </p>
      </div>
    </div>
  );
}
