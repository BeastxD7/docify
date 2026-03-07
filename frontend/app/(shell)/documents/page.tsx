"use client";

import { useEffect, useState } from "react";
import { toast } from "sonner";
import { FileText, Hash, Clock } from "lucide-react";
import { Card, CardContent } from "@/components/ui/card";
import { Badge } from "@/components/ui/badge";
import { listDocuments, type Document } from "@/lib/api";

export default function DocumentsPage() {
  const [docs, setDocs] = useState<Document[]>([]);
  const [loading, setLoading] = useState(true);

  useEffect(() => {
    listDocuments()
      .then((r) => setDocs(r.data))
      .catch(() => toast.error("Failed to load documents"))
      .finally(() => setLoading(false));
  }, []);

  return (
    <div className="flex flex-col gap-6">
      <div>
        <h2 className="text-xl font-semibold">Documents</h2>
        <p className="text-sm text-muted-foreground">{docs.length} indexed document{docs.length !== 1 ? "s" : ""}</p>
      </div>

      {loading ? (
        <div className="grid grid-cols-1 gap-3 sm:grid-cols-2 lg:grid-cols-3">
          {Array.from({ length: 3 }).map((_, i) => (
            <Card key={i} className="animate-pulse">
              <CardContent className="p-4 h-24" />
            </Card>
          ))}
        </div>
      ) : docs.length === 0 ? (
        <div className="flex flex-col items-center gap-3 py-20 text-muted-foreground">
          <FileText className="h-10 w-10 opacity-30" />
          <p className="text-sm">No documents yet — upload some first</p>
        </div>
      ) : (
        <div className="grid grid-cols-1 gap-3 sm:grid-cols-2 lg:grid-cols-3">
          {docs.map((doc) => (
            <Card key={doc.id} className="hover:border-primary/50 transition-colors">
              <CardContent className="flex flex-col gap-3 p-4">
                <div className="flex items-start gap-3">
                  <FileText className="h-5 w-5 shrink-0 text-muted-foreground mt-0.5" />
                  <p className="font-medium text-sm leading-snug break-all">{doc.filename}</p>
                </div>
                <div className="flex items-center gap-2 flex-wrap">
                  {doc.total_chunks ? (
                    <Badge variant="secondary" className="gap-1 text-xs">
                      <Hash className="h-3 w-3" />{doc.total_chunks} chunks
                    </Badge>
                  ) : (
                    <Badge variant="outline" className="text-xs">Processing…</Badge>
                  )}
                  <span className="flex items-center gap-1 text-xs text-muted-foreground ml-auto">
                    <Clock className="h-3 w-3" />
                    {new Date(doc.created_at).toLocaleDateString()}
                  </span>
                </div>
              </CardContent>
            </Card>
          ))}
        </div>
      )}
    </div>
  );
}
