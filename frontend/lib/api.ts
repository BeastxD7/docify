const BASE = process.env.NEXT_PUBLIC_API_URL ?? "http://localhost:8000";

async function request<T>(path: string, init?: RequestInit): Promise<T> {
  const res = await fetch(`${BASE}${path}`, init);
  const json = await res.json();
  if (!res.ok) throw new Error(json?.message ?? "Request failed");
  return json;
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

export async function uploadDocument(file: File): Promise<ApiSuccess<{ job_id: string; doc_id: string; filename: string }>> {
  const form = new FormData();
  form.append("file", file);
  return request("/upload", { method: "POST", body: form });
}

export async function getJobStatus(jobId: string): Promise<ApiSuccess<JobStatus>> {
  return request(`/status/${jobId}`);
}

export async function listDocuments(): Promise<ApiSuccess<Document[]>> {
  return request("/documents");
}

export async function queryDocuments(
  question: string,
  docIds: string[] | null = null,
  topK = 8,
): Promise<ApiSuccess<QueryResult>> {
  return request("/query", {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({ question, doc_ids: docIds, top_k: topK }),
  });
}
