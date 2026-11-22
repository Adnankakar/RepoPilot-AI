import React, { useCallback, useEffect, useRef, useState } from "react";
import {
  listRepositories,
  deleteRepository,
  triggerReindex,
  RepositoryResponse,
} from "../api";
import RepoForm from "../components/RepoForm";
import IndexingProgress from "../components/IndexingProgress";
import {
  GitBranch,
  Database,
  CheckCircle2,
  Clock,
  XCircle,
  RefreshCw,
  Trash2,
  RotateCcw,
  Loader2,
  AlertTriangle,
  ExternalLink,
} from "lucide-react";

// ─── Status helpers ───────────────────────────────────────────────────────────

const STATUS_STYLES: Record<string, { pill: string; label: string }> = {
  pending:  { pill: "bg-gray-100 text-gray-500 border border-gray-200",   label: "Pending" },
  indexing: { pill: "bg-blue-100 text-blue-700 border border-blue-200",   label: "Indexing" },
  indexed:  { pill: "bg-emerald-100 text-emerald-700 border border-emerald-200", label: "Indexed" },
  failed:   { pill: "bg-red-100 text-red-600 border border-red-200",      label: "Failed" },
  error:    { pill: "bg-red-100 text-red-600 border border-red-200",      label: "Error" },
  queued:   { pill: "bg-amber-100 text-amber-700 border border-amber-200", label: "Queued" },
};

function StatusPill({ status }: { status: string }) {
  const s = STATUS_STYLES[status] ?? { pill: "bg-gray-100 text-gray-500 border border-gray-200", label: status };
  return (
    <span className={`inline-flex items-center text-xs font-medium px-2.5 py-0.5 rounded-full capitalize ${s.pill}`}>
      {s.label}
    </span>
  );
}

function StatusIcon({ status }: { status: string }) {
  if (status === "indexed")
    return <CheckCircle2 className="w-4 h-4 text-emerald-500 shrink-0" />;
  if (status === "failed" || status === "error")
    return <XCircle className="w-4 h-4 text-red-500 shrink-0" />;
  if (status === "indexing" || status === "pending" || status === "queued")
    return <Clock className="w-4 h-4 text-blue-400 shrink-0" />;
  return <GitBranch className="w-4 h-4 text-gray-400 shrink-0" />;
}

// ─── Delete confirmation modal ────────────────────────────────────────────────

interface DeleteModalProps {
  repo: RepositoryResponse;
  onConfirm: () => void;
  onCancel: () => void;
  deleting: boolean;
}

function DeleteModal({ repo, onConfirm, onCancel, deleting }: DeleteModalProps) {
  // Close on Escape
  useEffect(() => {
    const handler = (e: KeyboardEvent) => { if (e.key === "Escape") onCancel(); };
    window.addEventListener("keydown", handler);
    return () => window.removeEventListener("keydown", handler);
  }, [onCancel]);

  return (
    <div
      className="fixed inset-0 z-50 flex items-center justify-center bg-black/40 backdrop-blur-sm"
      onClick={(e) => { if (e.target === e.currentTarget) onCancel(); }}
    >
      <div className="bg-white rounded-2xl shadow-2xl w-full max-w-md mx-4 overflow-hidden">
        <div className="flex items-center gap-3 px-6 py-5 border-b border-gray-100">
          <div className="bg-red-100 p-2 rounded-lg">
            <Trash2 className="w-5 h-5 text-red-600" />
          </div>
          <div>
            <h3 className="text-base font-semibold text-gray-900">Delete repository?</h3>
            <p className="text-xs text-gray-400 mt-0.5">This cannot be undone</p>
          </div>
        </div>

        <div className="px-6 py-5 space-y-3">
          <p className="text-sm text-gray-600">
            All indexed chunks, embeddings, and job history for{" "}
            <span className="font-mono text-gray-800 bg-gray-100 px-1.5 py-0.5 rounded text-xs">
              {repo.url.replace("https://github.com/", "")}
            </span>{" "}
            will be permanently deleted along with the local clone.
          </p>
          {(repo.status === "indexing" || repo.status === "queued") && (
            <div className="flex items-start gap-2 bg-amber-50 border border-amber-200 rounded-lg px-3 py-2.5">
              <AlertTriangle className="w-4 h-4 text-amber-600 shrink-0 mt-0.5" />
              <p className="text-xs text-amber-700">
                An indexing job is currently <strong>{repo.status}</strong>. You may need to wait for
                it to finish before deletion is allowed.
              </p>
            </div>
          )}
        </div>

        <div className="flex justify-end gap-3 px-6 py-4 bg-gray-50 border-t border-gray-100">
          <button
            onClick={onCancel}
            disabled={deleting}
            className="px-4 py-2 text-sm font-medium text-gray-700 bg-white border border-gray-200 rounded-lg hover:bg-gray-50 transition disabled:opacity-50"
          >
            Cancel
          </button>
          <button
            onClick={onConfirm}
            disabled={deleting}
            className="flex items-center gap-2 px-4 py-2 text-sm font-medium text-white bg-red-600 hover:bg-red-700 rounded-lg transition disabled:opacity-60"
          >
            {deleting ? <Loader2 className="w-3.5 h-3.5 animate-spin" /> : <Trash2 className="w-3.5 h-3.5" />}
            {deleting ? "Deleting…" : "Delete permanently"}
          </button>
        </div>
      </div>
    </div>
  );
}

// ─── Repo card ────────────────────────────────────────────────────────────────

interface RepoCardProps {
  repo: RepositoryResponse;
  onDelete: (repo: RepositoryResponse) => void;
  onReindex: (repo: RepositoryResponse) => void;
  reindexingId: string | null;
}

function RepoCard({ repo, onDelete, onReindex, reindexingId }: RepoCardProps) {
  const isReindexing = reindexingId === repo.id;
  const canReindex = repo.status === "indexed" || repo.status === "failed" || repo.status === "error";
  const shortName = repo.url.replace(/^https?:\/\/(www\.)?github\.com\//, "");

  return (
    <div className="group flex items-center gap-4 bg-white border border-gray-200 hover:border-gray-300 rounded-xl px-5 py-4 shadow-sm transition">
      <StatusIcon status={repo.status} />

      <div className="flex-1 min-w-0">
        <div className="flex items-center gap-2 min-w-0">
          <p className="text-sm font-semibold text-gray-800 truncate">{shortName}</p>
          <a
            href={repo.url}
            target="_blank"
            rel="noopener noreferrer"
            className="shrink-0 text-gray-300 hover:text-blue-500 transition opacity-0 group-hover:opacity-100"
            title="Open on GitHub"
          >
            <ExternalLink className="w-3.5 h-3.5" />
          </a>
        </div>
        <p className="text-xs text-gray-400 mt-0.5 truncate">
          {repo.provider} · <span className="font-mono">{repo.default_branch}</span>
          {repo.indexed_commit && (
            <> · <span className="font-mono">{repo.indexed_commit.slice(0, 7)}</span></>
          )}
          <span className="ml-2">{new Date(repo.created_at).toLocaleDateString()}</span>
        </p>
      </div>

      <div className="flex items-center gap-2 shrink-0">
        <StatusPill status={repo.status} />

        {canReindex && (
          <button
            onClick={() => onReindex(repo)}
            disabled={isReindexing}
            title="Re-index this repository"
            className="p-1.5 rounded-lg text-gray-400 hover:text-blue-600 hover:bg-blue-50 transition disabled:opacity-40 opacity-0 group-hover:opacity-100"
          >
            {isReindexing
              ? <Loader2 className="w-3.5 h-3.5 animate-spin" />
              : <RotateCcw className="w-3.5 h-3.5" />}
          </button>
        )}

        <button
          onClick={() => onDelete(repo)}
          title="Delete repository"
          className="p-1.5 rounded-lg text-gray-400 hover:text-red-600 hover:bg-red-50 transition opacity-0 group-hover:opacity-100"
        >
          <Trash2 className="w-3.5 h-3.5" />
        </button>
      </div>
    </div>
  );
}

// ─── Active job tracker ───────────────────────────────────────────────────────

interface ActiveJob { repoId: string; jobId: string }

// ─── Page ─────────────────────────────────────────────────────────────────────

export default function DashboardPage() {
  const [repos, setRepos]           = useState<RepositoryResponse[]>([]);
  const [loading, setLoading]       = useState(true);
  const [activeJob, setActiveJob]   = useState<ActiveJob | null>(null);
  const [deleteTarget, setDeleteTarget] = useState<RepositoryResponse | null>(null);
  const [deleting, setDeleting]     = useState(false);
  const [deleteError, setDeleteError] = useState<string | null>(null);
  const [reindexingId, setReindexingId] = useState<string | null>(null);
  const [reindexError, setReindexError] = useState<string | null>(null);

  const fetchRepos = useCallback(async () => {
    setLoading(true);
    try {
      setRepos(await listRepositories());
    } catch {
      /* non-fatal */
    } finally {
      setLoading(false);
    }
  }, []);

  useEffect(() => { fetchRepos(); }, [fetchRepos]);

  const handleIndexingStarted = (repoId: string, jobId: string) => {
    setActiveJob({ repoId, jobId });
    fetchRepos();
  };

  const handleJobDone = () => {
    fetchRepos();
    setTimeout(() => setActiveJob(null), 3000);
  };

  // ── Delete flow ────────────────────────────────────────────────────────────
  const handleDeleteConfirm = async () => {
    if (!deleteTarget) return;
    setDeleting(true);
    setDeleteError(null);
    try {
      await deleteRepository(deleteTarget.id);
      setDeleteTarget(null);
      // If the deleted repo was being tracked as an active job, clear it
      if (activeJob?.repoId === deleteTarget.id) setActiveJob(null);
      await fetchRepos();
    } catch (err: unknown) {
      setDeleteError(err instanceof Error ? err.message : "Delete failed.");
    } finally {
      setDeleting(false);
    }
  };

  // ── Re-index flow ──────────────────────────────────────────────────────────
  const handleReindex = async (repo: RepositoryResponse) => {
    setReindexError(null);
    setReindexingId(repo.id);
    try {
      const result = await triggerReindex(repo.id);
      setActiveJob({ repoId: repo.id, jobId: result.job_id });
      await fetchRepos();
    } catch (err: unknown) {
      setReindexError(err instanceof Error ? err.message : "Re-index failed.");
    } finally {
      setReindexingId(null);
    }
  };

  // ── Stats ──────────────────────────────────────────────────────────────────
  const indexed = repos.filter((r) => r.status === "indexed").length;
  const failed  = repos.filter((r) => r.status === "failed" || r.status === "error").length;
  const active  = repos.filter((r) => r.status === "indexing" || r.status === "queued" || r.status === "pending").length;

  return (
    <div className="p-8 max-w-4xl mx-auto space-y-8">

      {/* ── Header ─────────────────────────────────────────────────────── */}
      <div>
        <h1 className="text-2xl font-bold text-gray-900 flex items-center gap-2.5">
          <Database className="w-6 h-6 text-blue-600" />
          Dashboard
        </h1>
        <p className="text-gray-500 text-sm mt-1">
          Index GitHub repositories and monitor their status.
        </p>
      </div>

      {/* ── Stats ──────────────────────────────────────────────────────── */}
      <div className="grid grid-cols-2 sm:grid-cols-4 gap-4">
        {[
          { label: "Total",    value: repos.length, icon: GitBranch,   color: "text-blue-500",    bg: "bg-blue-50" },
          { label: "Indexed",  value: indexed,       icon: CheckCircle2, color: "text-emerald-600", bg: "bg-emerald-50" },
          { label: "Active",   value: active,        icon: Clock,       color: "text-amber-500",   bg: "bg-amber-50" },
          { label: "Failed",   value: failed,        icon: XCircle,     color: "text-red-500",     bg: "bg-red-50" },
        ].map(({ label, value, icon: Icon, color, bg }) => (
          <div key={label} className="bg-white border border-gray-200 rounded-xl px-5 py-4 shadow-sm">
            <div className="flex items-center justify-between mb-2">
              <p className="text-xs font-medium text-gray-500">{label}</p>
              <div className={`${bg} p-1.5 rounded-lg`}>
                <Icon className={`w-4 h-4 ${color}`} />
              </div>
            </div>
            <p className="text-3xl font-bold text-gray-900">{value}</p>
          </div>
        ))}
      </div>

      {/* ── Add repository ──────────────────────────────────────────────── */}
      <div className="bg-white rounded-2xl border border-gray-200 shadow-sm p-6 space-y-4">
        <h2 className="text-base font-semibold text-gray-800">Index a Repository</h2>
        <RepoForm onIndexingStarted={handleIndexingStarted} />
      </div>

      {/* ── Re-index error ──────────────────────────────────────────────── */}
      {reindexError && (
        <div className="flex items-start gap-2 text-sm text-red-700 bg-red-50 border border-red-200 rounded-lg px-4 py-3">
          <XCircle className="w-4 h-4 shrink-0 mt-0.5" />
          <div>
            <span className="font-semibold">Re-index failed: </span>{reindexError}
          </div>
          <button onClick={() => setReindexError(null)} className="ml-auto text-red-400 hover:text-red-600">✕</button>
        </div>
      )}

      {/* ── Delete error ────────────────────────────────────────────────── */}
      {deleteError && (
        <div className="flex items-start gap-2 text-sm text-red-700 bg-red-50 border border-red-200 rounded-lg px-4 py-3">
          <XCircle className="w-4 h-4 shrink-0 mt-0.5" />
          <div>
            <span className="font-semibold">Delete failed: </span>{deleteError}
          </div>
          <button onClick={() => setDeleteError(null)} className="ml-auto text-red-400 hover:text-red-600">✕</button>
        </div>
      )}

      {/* ── Active job progress ─────────────────────────────────────────── */}
      {activeJob && (
        <div>
          <h2 className="text-sm font-semibold text-gray-700 mb-3">Active Indexing Job</h2>
          <IndexingProgress
            repoId={activeJob.repoId}
            jobId={activeJob.jobId}
            onDone={handleJobDone}
          />
        </div>
      )}

      {/* ── Repository list ──────────────────────────────────────────────── */}
      <div>
        <div className="flex items-center justify-between mb-3">
          <h2 className="text-sm font-semibold text-gray-700">
            Repositories{repos.length > 0 ? ` (${repos.length})` : ""}
          </h2>
          <button
            onClick={fetchRepos}
            disabled={loading}
            className="flex items-center gap-1.5 text-xs text-gray-400 hover:text-blue-600 transition disabled:opacity-40"
          >
            <RefreshCw className={`w-3.5 h-3.5 ${loading ? "animate-spin" : ""}`} />
            Refresh
          </button>
        </div>

        {loading ? (
          <div className="space-y-3">
            {[1, 2, 3].map((i) => (
              <div key={i} className="bg-gray-100 rounded-xl h-16 animate-pulse" />
            ))}
          </div>
        ) : repos.length === 0 ? (
          <div className="text-center py-16 border border-dashed border-gray-200 rounded-2xl text-gray-400">
            <GitBranch className="w-10 h-10 mx-auto mb-3 opacity-30" />
            <p className="text-sm">No repositories yet.</p>
            <p className="text-xs mt-1 text-gray-300">Use the form above to add one.</p>
          </div>
        ) : (
          <div className="space-y-2.5">
            {repos.map((r) => (
              <RepoCard
                key={r.id}
                repo={r}
                onDelete={setDeleteTarget}
                onReindex={handleReindex}
                reindexingId={reindexingId}
              />
            ))}
          </div>
        )}
      </div>

      {/* ── Delete confirmation modal ────────────────────────────────────── */}
      {deleteTarget && (
        <DeleteModal
          repo={deleteTarget}
          onConfirm={handleDeleteConfirm}
          onCancel={() => { setDeleteTarget(null); setDeleteError(null); }}
          deleting={deleting}
        />
      )}
    </div>
  );
}
