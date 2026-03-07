const BASE = process.env.NEXT_PUBLIC_API_URL ?? "http://localhost:8000";

async function request<T>(path: string, init?: RequestInit): Promise<ApiSuccess<T>> {
  const res = await fetch(`${BASE}${path}`, init);
  const json = await res.json();
  if (!res.ok) throw new Error(json?.message ?? json?.detail ?? "Request failed");
  // Handle new wrapped format { status, data, ... } and old raw format
  if (json?.status === "success") return json as ApiSuccess<T>;
  return { status_code: res.status, status: "success", message: "", data: json as T };
}

// ── Types ──────────────────────────────────────────────────────────────────

export interface ApiSuccess<T> {
  status_code: number;
  status: "success";
  message: string;
  data: T;
}

export interface Document {
  id: string;
  filename: string;
  total_chunks: string | null;
  created_at: string;
}

export interface JobStatus {
  job_id: string;
  doc_id: string;
  filename: string;
  status: "pending" | "processing" | "completed" | "failed";
  error: string | null;
  created_at: string;
  updated_at: string;
}

export interface Source {
  filename: string;
  page_number: number;
  doc_id: string;
  score: number;
  excerpt: string;
}

export interface QueryResult {
  answer: string;
  sources: Source[];
}

// ── API calls ──────────────────────────────────────────────────────────────

export function uploadDocument(file: File) {
  const form = new FormData();
  form.append("file", file);
  return request<{ job_id: string; doc_id: string; filename: string }>("/upload", { method: "POST", body: form });
}

export function getJobStatus(jobId: string) {
  return request<JobStatus>(`/status/${jobId}`);
}

export function listDocuments() {
  return request<Document[]>("/documents");
}

export function queryDocuments(question: string, docIds: string[] | null = null, topK = 8) {
  return request<QueryResult>("/query", {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({ question, doc_ids: docIds, top_k: topK }),
  });
}
