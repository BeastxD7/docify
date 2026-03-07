import { Chat } from "@/components/chat";

export default function ChatPage() {
  return (
    <div className="flex h-full flex-col gap-4">
      <div>
        <h2 className="text-xl font-semibold">Chat</h2>
        <p className="text-sm text-muted-foreground">Ask questions across your indexed documents</p>
      </div>
      <div className="flex-1 min-h-0">
        <Chat />
      </div>
    </div>
  );
}
