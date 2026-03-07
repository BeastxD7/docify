"use client";

import { useCallback, useState } from "react";
import { useDropzone } from "react-dropzone";
import { toast } from "sonner";
import { Upload, FileText, CheckCircle, XCircle, Loader2 } from "lucide-react";
import { Card, CardContent } from "@/components/ui/card";
import { Badge } from "@/components/ui/badge";
import { Progress } from "@/components/ui/progress";
import { cn } from "@/lib/utils";
import { uploadDocument, getJobStatus } from "@/lib/api";

interface UploadedFile {
  name: string;
  jobId: string;
  docId: string;
  status: "pending" | "processing" | "completed" | "failed";
  error?: string;
}

export function UploadZone({ onCompleted }: { onCompleted?: () => void }) {
  const [files, setFiles] = useState<UploadedFile[]>([]);

  const pollStatus = useCallback(async (jobId: string) => {
    const interval = setInterval(async () => {
      try {
        const res = await getJobStatus(jobId);
        const { status, error } = res.data;
        setFiles((prev) =>
          prev.map((f) => (f.jobId === jobId ? { ...f, status, error: error ?? undefined } : f)),
        );
        if (status === "completed") {
          clearInterval(interval);
          toast.success("Document processed and ready to query!");
          onCompleted?.();
        }
        if (status === "failed") {
          clearInterval(interval);
          toast.error(`Processing failed: ${error}`);
        }
      } catch {
        clearInterval(interval);
      }
    }, 2000);
  }, [onCompleted]);

  const onDrop = useCallback(
    async (accepted: File[]) => {
      for (const file of accepted) {
        try {
          const res = await uploadDocument(file);
          const { job_id, doc_id } = res.data;
          setFiles((prev) => [...prev, { name: file.name, jobId: job_id, docId: doc_id, status: "pending" }]);
          toast.info(`"${file.name}" uploaded — processing…`);
          pollStatus(job_id);
        } catch (e: unknown) {
          toast.error(`Upload failed: ${e instanceof Error ? e.message : "Unknown error"}`);
        }
      }
    },
    [pollStatus],
  );

  const { getRootProps, getInputProps, isDragActive } = useDropzone({
    onDrop,
    accept: { "application/pdf": [".pdf"], "application/vnd.openxmlformats-officedocument.wordprocessingml.document": [".docx"], "text/plain": [".txt"] },
    multiple: true,
  });

  return (
    <div className="flex flex-col gap-4">
      <div
        {...getRootProps()}
        className={cn(
          "flex cursor-pointer flex-col items-center justify-center gap-3 rounded-xl border-2 border-dashed p-12 text-center transition-colors",
          isDragActive
            ? "border-primary bg-primary/5 text-primary"
            : "border-border text-muted-foreground hover:border-primary/50 hover:text-foreground",
        )}
      >
        <input {...getInputProps()} />
        <Upload className="h-10 w-10" />
        <div>
          <p className="font-medium">{isDragActive ? "Drop files here" : "Drag & drop files here"}</p>
          <p className="text-sm mt-1">or click to browse — PDF, DOCX, TXT</p>
        </div>
      </div>

      {files.length > 0 && (
        <div className="flex flex-col gap-2">
          {files.map((f) => (
            <Card key={f.jobId}>
              <CardContent className="flex items-center gap-3 py-3 px-4">
                <FileText className="h-4 w-4 shrink-0 text-muted-foreground" />
                <span className="flex-1 truncate text-sm font-medium">{f.name}</span>
                <StatusBadge status={f.status} />
              </CardContent>
              {(f.status === "pending" || f.status === "processing") && (
                <Progress value={f.status === "processing" ? 60 : 20} className="h-0.5 rounded-none" />
              )}
            </Card>
          ))}
        </div>
      )}
    </div>
  );
}

function StatusBadge({ status }: { status: UploadedFile["status"] }) {
  if (status === "completed")
    return <Badge variant="default" className="gap-1 bg-green-600"><CheckCircle className="h-3 w-3" />Ready</Badge>;
  if (status === "failed")
    return <Badge variant="destructive" className="gap-1"><XCircle className="h-3 w-3" />Failed</Badge>;
  if (status === "processing")
    return <Badge variant="secondary" className="gap-1"><Loader2 className="h-3 w-3 animate-spin" />Processing</Badge>;
  return <Badge variant="outline" className="gap-1"><Loader2 className="h-3 w-3 animate-spin" />Queued</Badge>;
}
