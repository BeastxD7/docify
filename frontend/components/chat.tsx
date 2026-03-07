"use client";

import { useEffect, useRef, useState } from "react";
import { toast } from "sonner";
import { Send, Loader2, Bot, User, BookOpen } from "lucide-react";
import { Button } from "@/components/ui/button";
import { Textarea } from "@/components/ui/textarea";
import { Badge } from "@/components/ui/badge";
import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card";
import { ScrollArea } from "@/components/ui/scroll-area";
import { Separator } from "@/components/ui/separator";
import { cn } from "@/lib/utils";
import { queryDocuments, listDocuments, type Document, type Source } from "@/lib/api";

interface Message {
  role: "user" | "assistant";
  content: string;
  sources?: Source[];
}

export function Chat() {
  const [docs, setDocs] = useState<Document[]>([]);
  const [selectedIds, setSelectedIds] = useState<string[]>([]);
  const [messages, setMessages] = useState<Message[]>([]);
  const [input, setInput] = useState("");
  const [loading, setLoading] = useState(false);
  const bottomRef = useRef<HTMLDivElement>(null);

  useEffect(() => {
    listDocuments()
      .then((r) => setDocs(r.data))
      .catch(() => toast.error("Failed to load documents"));
  }, []);

  useEffect(() => {
    bottomRef.current?.scrollIntoView({ behavior: "smooth" });
  }, [messages]);

  const toggleDoc = (id: string) =>
    setSelectedIds((prev) => (prev.includes(id) ? prev.filter((x) => x !== id) : [...prev, id]));

  const send = async () => {
    const question = input.trim();
    if (!question || loading) return;
    setInput("");
    setMessages((prev) => [...prev, { role: "user", content: question }]);
    setLoading(true);
    try {
      const res = await queryDocuments(question, selectedIds.length ? selectedIds : null);
      setMessages((prev) => [
        ...prev,
        { role: "assistant", content: res.data.answer, sources: res.data.sources },
      ]);
    } catch (e: unknown) {
      toast.error(e instanceof Error ? e.message : "Query failed");
      setMessages((prev) => [
        ...prev,
        { role: "assistant", content: "Sorry, something went wrong. Please try again." },
      ]);
    } finally {
      setLoading(false);
    }
  };

  const handleKey = (e: React.KeyboardEvent) => {
    if (e.key === "Enter" && !e.shiftKey) {
      e.preventDefault();
      send();
    }
  };

  return (
    <div className="flex h-full gap-4">
      {/* Document selector */}
      <div className="w-56 shrink-0">
        <Card className="h-full flex flex-col">
          <CardHeader className="pb-3">
            <CardTitle className="text-sm font-medium flex items-center gap-2">
              <BookOpen className="h-4 w-4" />
              Documents
            </CardTitle>
            <p className="text-xs text-muted-foreground">
              {selectedIds.length === 0 ? "Searching all" : `${selectedIds.length} selected`}
            </p>
          </CardHeader>
          <Separator />
          <ScrollArea className="flex-1 px-3 py-2">
            {docs.length === 0 ? (
              <p className="text-xs text-muted-foreground py-4 text-center">No documents yet</p>
            ) : (
              <div className="flex flex-col gap-1">
                {docs.map((doc) => (
                  <button
                    key={doc.id}
                    onClick={() => toggleDoc(doc.id)}
                    className={cn(
                      "w-full rounded-md px-2 py-2 text-left text-xs transition-colors",
                      selectedIds.includes(doc.id)
                        ? "bg-primary text-primary-foreground"
                        : "hover:bg-accent text-muted-foreground hover:text-foreground",
                    )}
                  >
                    <p className="font-medium truncate">{doc.filename}</p>
                    {doc.total_chunks && (
                      <p className="opacity-70 mt-0.5">{doc.total_chunks} chunks</p>
                    )}
                  </button>
                ))}
              </div>
            )}
          </ScrollArea>
        </Card>
      </div>

      {/* Chat area */}
      <div className="flex flex-1 flex-col gap-3 min-w-0">
        <ScrollArea className="flex-1 rounded-xl border border-border bg-card p-4">
          {messages.length === 0 ? (
            <div className="flex h-full flex-col items-center justify-center gap-2 py-20 text-center text-muted-foreground">
              <Bot className="h-10 w-10 opacity-30" />
              <p className="text-sm">Ask anything about your documents</p>
              <p className="text-xs opacity-60">Select specific documents on the left, or search across all</p>
            </div>
          ) : (
            <div className="flex flex-col gap-6">
              {messages.map((msg, i) => (
                <div key={i} className={cn("flex gap-3", msg.role === "user" && "flex-row-reverse")}>
                  <div className={cn(
                    "flex h-7 w-7 shrink-0 items-center justify-center rounded-full text-xs",
                    msg.role === "user" ? "bg-primary text-primary-foreground" : "bg-muted",
                  )}>
                    {msg.role === "user" ? <User className="h-3.5 w-3.5" /> : <Bot className="h-3.5 w-3.5" />}
                  </div>
                  <div className="flex flex-col gap-2 max-w-[80%]">
                    <div className={cn(
                      "rounded-2xl px-4 py-2.5 text-sm leading-relaxed",
                      msg.role === "user"
                        ? "bg-primary text-primary-foreground rounded-tr-sm"
                        : "bg-muted rounded-tl-sm",
                    )}>
                      {msg.content}
                    </div>
                    {msg.sources && msg.sources.length > 0 && (
                      <div className="flex flex-col gap-1.5 px-1">
                        <p className="text-xs text-muted-foreground font-medium">Sources</p>
                        {msg.sources.map((src, j) => (
                          <div key={j} className="rounded-lg border border-border bg-card/50 px-3 py-2 text-xs">
                            <div className="flex items-center justify-between gap-2 mb-1">
                              <span className="font-medium truncate">{src.filename}</span>
                              <div className="flex items-center gap-1.5 shrink-0">
                                <Badge variant="outline" className="text-[10px] h-4 px-1.5">p.{src.page_number}</Badge>
                                <Badge variant="outline" className="text-[10px] h-4 px-1.5">{(src.score * 100).toFixed(0)}%</Badge>
                              </div>
                            </div>
                            <p className="text-muted-foreground line-clamp-2">{src.excerpt}</p>
                          </div>
                        ))}
                      </div>
                    )}
                  </div>
                </div>
              ))}
              {loading && (
                <div className="flex gap-3">
                  <div className="flex h-7 w-7 shrink-0 items-center justify-center rounded-full bg-muted">
                    <Bot className="h-3.5 w-3.5" />
                  </div>
                  <div className="rounded-2xl rounded-tl-sm bg-muted px-4 py-2.5">
                    <Loader2 className="h-4 w-4 animate-spin text-muted-foreground" />
                  </div>
                </div>
              )}
              <div ref={bottomRef} />
            </div>
          )}
        </ScrollArea>

        <div className="flex gap-2">
          <Textarea
            value={input}
            onChange={(e) => setInput(e.target.value)}
            onKeyDown={handleKey}
            placeholder="Ask a question… (Enter to send, Shift+Enter for newline)"
            className="min-h-[52px] max-h-32 resize-none"
            disabled={loading}
          />
          <Button onClick={send} disabled={!input.trim() || loading} size="icon" className="h-auto w-12 shrink-0">
            {loading ? <Loader2 className="h-4 w-4 animate-spin" /> : <Send className="h-4 w-4" />}
          </Button>
        </div>
      </div>
    </div>
  );
}
