/**
 * api.ts – Centralised API client for RepoPilot AI
 */

const BASE = import.meta.env.VITE_API_BASE_URL ?? "";

// ── Token store ──────────────────────────────────────────────────────────────
let _token: string | null = localStorage.getItem("rp_token");

export function setToken(t: string | null) {
  _token = t;
  if (t) localStorage.setItem("rp_token", t);
  else localStorage.removeItem("rp_token");
}

export function getToken() {
  return _token;
}

function authHeaders(): Record<string, string> {
  return _token ? { Authorization: `Bearer ${_token}` } : {};
}

async function request<T>(path: string, init: RequestInit = {}): Promise<T> {
  const url = `${BASE}${path}`;

  let res: Response;
  try {
    res = await fetch(url, {
      ...init,
      headers: {
        "Content-Type": "application/json",
        ...authHeaders(),
        ...(init.headers as Record<string, string> | undefined),
      },
    });
  } catch (networkErr) {
    throw new Error(
      `NetworkError: ${networkErr instanceof Error ? networkErr.message : String(networkErr)}`
    );
  }

  if (!res.ok) {
    let detail = `HTTP ${res.status}`;
    try {
      const body = await res.json();
      if (typeof body?.detail === "string") {
        detail = `${res.status} ${body.detail}`;
      } else if (Array.isArray(body?.detail)) {
        detail =
          `${res.status} ` +
          body.detail
            .map(
              (e: { loc?: string[]; msg?: string }) =>
                `${(e.loc ?? []).join(".")}: ${e.msg ?? "validation error"}`
            )
            .join("; ");
      } else {
        detail = `${res.status} ${JSON.stringify(body)}`;
      }
    } catch {
      /* body was not JSON */
    }
    throw new Error(detail);
  }

  const text = await res.text();
  return text ? (JSON.parse(text) as T) : (undefined as unknown as T);
}

// ── Auth ─────────────────────────────────────────────────────────────────────
export interface TokenResponse {
  access_token: string;
  token_type: string;
}

export interface UserResponse {
  id: string;
  email: string;
  role: string;
}

export async function login(email: string, password: string): Promise<TokenResponse> {
  return request<TokenResponse>("/api/auth/login", {
    method: "POST",
    body: JSON.stringify({ email, password }),
  });
}

export async function register(
  email: string,
  password: string,
  role = "developer"
): Promise<UserResponse> {
  return request<UserResponse>("/api/auth/register", {
    method: "POST",
    body: JSON.stringify({ email, password, role }),
  });
}

export async function getMe(): Promise<UserResponse> {
  return request<UserResponse>("/api/auth/me");
}

// ── Repositories ─────────────────────────────────────────────────────────────
export interface RepositoryResponse {
  id: string;
  owner_id: string;
  provider: string;
  external_id: string;
  url: string;
  default_branch: string;
  indexed_commit: string | null;
  status: string;
  created_at: string;
}

export interface RepositoryRegistrationResponse {
  repository: RepositoryResponse;
  indexing_job_id: string;
  job_id: string;
  message: string;
}

export async function registerRepository(
  url: string
): Promise<RepositoryRegistrationResponse> {
  return request<RepositoryRegistrationResponse>("/api/repositories", {
    method: "POST",
    body: JSON.stringify({ url }),
  });
}

export async function listRepositories(): Promise<RepositoryResponse[]> {
  return request<RepositoryResponse[]>("/api/repositories");
}

export async function deleteRepository(repoId: string): Promise<void> {
  return request<void>(`/api/repositories/${repoId}`, { method: "DELETE" });
}

// ── Indexing jobs ─────────────────────────────────────────────────────────────
export interface IndexingJobResponse {
  id: string;
  repository_id: string;
  status: string;
  attempt_count: number;
  started_at: string | null;
  finished_at: string | null;
  error_summary: string | null;
  failed_stage: string | null;
  created_at: string;
  job_id: string | null;
}

export interface RepositoryStatusResponse {
  repository_id: string;
  status: string;
  latest_job: IndexingJobResponse | null;
}

export async function getRepositoryStatus(
  repoId: string
): Promise<RepositoryStatusResponse> {
  return request<RepositoryStatusResponse>(`/api/repositories/${repoId}/status`);
}

export async function getLatestJob(repoId: string): Promise<IndexingJobResponse> {
  return request<IndexingJobResponse>(`/api/repositories/${repoId}/jobs/latest`);
}

export async function triggerReindex(repoId: string): Promise<{ indexing_job_id: string; job_id: string }> {
  return request(`/api/repositories/${repoId}/jobs`, { method: "POST" });
}

export interface RepositoryFileSkipResponse {
  id: string;
  repository_id: string;
  path: string;
  reason: string;
}

export async function getRepositorySkips(
  repoId: string
): Promise<RepositoryFileSkipResponse[]> {
  return request<RepositoryFileSkipResponse[]>(`/api/repositories/${repoId}/skips`);
}

// ── Retrieval / Q&A ───────────────────────────────────────────────────────────
export interface RetrievedChunk {
  id: string;
  repository_id: string;
  file_path: string;
  chunk_index: number;
  start_line: number;
  end_line: number;
  content: string;
  similarity: number;
  distance: number;
  commit_sha: string | null;
}

export interface RetrievalResponse {
  question: string;
  has_sufficient_evidence: boolean;
  threshold: number;
  best_score: number | null;
  chunks: RetrievedChunk[];
  searched_repositories: string[];
  insufficient_evidence_reason: string | null;
  message: string;
}

export async function queryRetrieval(
  question: string,
  repositoryId?: string,
  topK = 5,
  similarityThreshold?: number
): Promise<RetrievalResponse> {
  return request<RetrievalResponse>("/api/retrieval/query", {
    method: "POST",
    body: JSON.stringify({
      question,
      repository_id: repositoryId ?? null,
      top_k: topK,
      ...(similarityThreshold !== undefined
        ? { similarity_threshold: similarityThreshold }
        : {}),
    }),
  });
}

// ── Chat / LLM Q&A ────────────────────────────────────────────────────────────
export interface ChatAskResponse {
  question: string;
  answer: string | null;
  has_sufficient_evidence: boolean;
  insufficient_evidence_reason: string | null;
  best_score: number | null;
  threshold: number;
  chunks_used: number;
  searched_repositories: string[];
}

export async function askQuestion(
  question: string,
  repositoryId?: string,
  topK = 5,
  similarityThreshold?: number
): Promise<ChatAskResponse> {
  return request<ChatAskResponse>("/api/chat/ask", {
    method: "POST",
    body: JSON.stringify({
      question,
      repository_id: repositoryId ?? null,
      top_k: topK,
      ...(similarityThreshold !== undefined
        ? { similarity_threshold: similarityThreshold }
        : {}),
    }),
  });
}
