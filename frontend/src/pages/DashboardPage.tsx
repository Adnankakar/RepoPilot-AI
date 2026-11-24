import React, { useCallback, useEffect, useState } from "react";
import {
  listRepositories, deleteRepository, triggerReindex, RepositoryResponse,
} from "../api";
import RepoForm from "../components/RepoForm";
import IndexingProgress from "../components/IndexingProgress";
import { useError } from "../context/ErrorContext";
import {
  GitBranch, LayoutGrid, CheckCircle2, Clock, XCircle,
  RefreshCw, Trash2, RotateCcw, Loader2, AlertTriangle, ExternalLink,
  Plus, ChevronRight,
} from "lucide-react";

// ── Shared design tokens ──────────────────────────────────────────────────────
const PAGE   = "min-h-screen bg-slate-50";
const INNER  = "max-w-5xl mx-auto px-6 py-8 space-y-8";
const CARD   = "bg-white rounded-2xl border border-slate-200 shadow-sm";
const SECT_TITLE = "text-xs font-bold text-slate-500 uppercase tracking-widest";

// ── Status config ─────────────────────────────────────────────────────────────
const STATUS_CFG: Record<string, { label: string; pill: string; ring: string }> = {
  pending:  { label: "Pending",  pill: "bg-slate-100 text-slate-500",     ring: "ring-slate-200"  },
  queued:   { label: "Queued",   pill: "bg-amber-100 text-amber-700",     ring: "ring-amber-200"  },
  indexing: { label: "Indexing", pill: "bg-blue-100  text-blue-700",      ring: "ring-blue-200"   },
  indexed:  { label: "Indexed",  pill: "bg-emerald-100 text-emerald-700", ring: "ring-emerald-200"},
  failed:   { label: "Failed",   pill: "bg-red-100   text-red-600",       ring: "ring-red-200"    },
  error:    { label: "Error",    pill: "bg-red-100   text-red-600",       ring: "ring-red-200"    },
};

function StatusPill({ status }: { status: string }) {
  const cfg = STATUS_CFG[status] ?? { label: status, pill: "bg-slate-100 text-slate-500", ring: "" };
  return (
    <span className={`inline-flex items-center text-xs font-semibold px-2.5 py-1 rounded-full capitalize ring-1 ${cfg.pill} ${cfg.ring}`}>
      {cfg.label}
    </span>
  );
}

function StatusDot({ status }: { status: string }) {
  const colors: Record<string, string> = {
    indexed: "bg-emerald-500", indexing: "bg-blue-500 animate-pulse",
    queued: "bg-amber-400 animate-pulse", pending: "bg-slate-300",
    failed: "bg-red-500", error: "bg-red-500",
  };
  return <span className={`w-2 h-2 rounded-full shrink-0 ${colors[status] ?? "bg-slate-300"}`} />;
}

// ── Delete confirmation modal ─────────────────────────────────────────────────
function DeleteModal({ repo, onConfirm, onCancel, busy }: {
  repo: RepositoryResponse; onConfirm: () => void; onCancel: () => void; busy: boolean;
}) {
  useEffect(() => {
    const h = (e: KeyboardEvent) => { if (e.key === "Escape") onCancel(); };
    window.addEventListener("keydown", h);
    return () => window.removeEventListener("keydown", h);
  }, [onCancel]);

  const short = repo.url.replace("https://github.com/", "");

  return (
    <div
      className="fixed inset-0 z-50 flex items-center justify-center bg-slate-900/60 backdrop-blur-sm"
      onClick={e => { if (e.target === e.currentTarget) onCancel(); }}
    >
      <div className={`${CARD} w-full max-w-md mx-4 shadow-2xl overflow-hidden`}>
        {/* Header */}
        <div className="flex items-center gap-3 px-6 py-5 border-b border-slate-100">
          <div className="bg-red-100 p-2.5 rounded-xl ring-1 ring-red-200">
            <Trash2 className="w-5 h-5 text-red-600" />
          </div>
          <div>
            <h3 className="text-base font-bold text-slate-900">Delete repository?</h3>
            <p className="text-xs text-slate-400 mt-0.5">This action cannot be undone</p>
          </div>
        </div>

        {/* Body */}
        <div className="px-6 py-5 space-y-3">
          <p className="text-sm text-slate-600 leading-relaxed">
            All chunks, embeddings, and job history for{" "}
            <code className="text-slate-800 bg-slate-100 px-1.5 py-0.5 rounded-lg text-xs font-mono">{short}</code>{" "}
            will be permanently removed along with the local clone.
          </p>
          {["indexing", "queued"].includes(repo.status) && (
            <div className="flex items-start gap-2 bg-amber-50 border border-amber-200 ring-1 ring-amber-100 rounded-xl px-4 py-3">
              <AlertTriangle className="w-4 h-4 text-amber-600 shrink-0 mt-0.5" />
              <p className="text-xs text-amber-700 leading-relaxed">
                An indexing job is currently <strong>{repo.status}</strong>. The server will reject the delete — wait for it to finish first.
              </p>
            </div>
          )}
        </div>

        {/* Footer */}
        <div className="flex justify-end gap-3 px-6 py-4 bg-slate-50 border-t border-slate-100">
          <button
            onClick={onCancel}
            disabled={busy}
            className="px-4 py-2 text-sm font-semibold text-slate-700 bg-white border border-slate-200 rounded-xl hover:bg-slate-100 transition disabled:opacity-50"
          >
            Cancel
          </button>
          <button
            onClick={onConfirm}
            disabled={busy}
            className="flex items-center gap-2 px-4 py-2 text-sm font-semibold text-white bg-red-600 hover:bg-red-700 rounded-xl transition disabled:opacity-60"
          >
            {busy ? <Loader2 className="w-3.5 h-3.5 animate-spin" /> : <Trash2 className="w-3.5 h-3.5" />}
            {busy ? "Deleting…" : "Delete permanently"}
          </button>
        </div>
      </div>
    </div>
  );
}

// ── Repo card ─────────────────────────────────────────────────────────────────
function RepoCard({ repo, onDelete, onReindex, reindexingId }: {
  repo: RepositoryResponse;
  onDelete: (r: RepositoryResponse) => void;
  onReindex: (r: RepositoryResponse) => void;
  reindexingId: string | null;
}) {
  const isRI  = reindexingId === repo.id;
  const canRI = ["indexed", "failed", "error"].includes(repo.status);
  const shortUrl = repo.url.replace(/^https?:\/\/(www\.)?github\.com\//, "");
  const owner = shortUrl.split("/")[0];
  const name  = shortUrl.split("/").slice(1).join("/");

  return (
    <div className="group flex items-center gap-4 bg-white border border-slate-200 hover:border-blue-200 hover:shadow-md rounded-2xl px-5 py-4 transition-all duration-150">
      <StatusDot status={repo.status} />

      {/* Repo info */}
      <div className="flex-1 min-w-0">
        <div className="flex items-center gap-2 min-w-0">
          <span className="text-xs text-slate-400 font-mono shrink-0">{owner}/</span>
          <span className="text-sm font-bold text-slate-900 truncate">{name}</span>
          <a
            href={repo.url}
            target="_blank"
            rel="noopener noreferrer"
            title="Open on GitHub"
            className="shrink-0 text-slate-300 hover:text-blue-500 opacity-0 group-hover:opacity-100 transition"
          >
            <ExternalLink className="w-3.5 h-3.5" />
          </a>
        </div>
        <div className="flex items-center gap-3 mt-1 text-xs text-slate-400 font-mono">
          <span className="capitalize">{repo.provider}</span>
          <span className="text-slate-200">·</span>
          <span>{repo.default_branch}</span>
          {repo.indexed_commit && (
            <><span className="text-slate-200">·</span><span>{repo.indexed_commit.slice(0, 7)}</span></>
          )}
          <span className="text-slate-200">·</span>
          <span>{new Date(repo.created_at).toLocaleDateString()}</span>
        </div>
      </div>

      {/* Actions */}
      <div className="flex items-center gap-2 shrink-0">
        <StatusPill status={repo.status} />

        {canRI && (
          <button
            onClick={() => onReindex(repo)}
            disabled={isRI}
            title="Re-index repository"
            className="p-2 rounded-xl text-slate-400 hover:text-blue-600 hover:bg-blue-50 transition opacity-0 group-hover:opacity-100 disabled:opacity-40"
          >
            {isRI
              ? <Loader2 className="w-4 h-4 animate-spin" />
              : <RotateCcw className="w-4 h-4" />}
          </button>
        )}

        <button
          onClick={() => onDelete(repo)}
          title="Delete repository"
          className="p-2 rounded-xl text-slate-400 hover:text-red-600 hover:bg-red-50 transition opacity-0 group-hover:opacity-100"
        >
          <Trash2 className="w-4 h-4" />
        </button>
      </div>
    </div>
  );
}

// ── Stats card ────────────────────────────────────────────────────────────────
function StatCard({ label, value, icon: Icon, colorCls, bgCls }: {
  label: string; value: number;
  icon: React.ElementType; colorCls: string; bgCls: string;
}) {
  return (
    <div className={`${CARD} px-5 py-4`}>
      <div className="flex items-center justify-between mb-3">
        <p className={`${SECT_TITLE}`}>{label}</p>
        <div className={`p-2 rounded-xl ${bgCls}`}>
          <Icon className={`w-4 h-4 ${colorCls}`} />
        </div>
      </div>
      <p className="text-3xl font-black text-slate-900 tracking-tight">{value}</p>
    </div>
  );
}

// ── Page ──────────────────────────────────────────────────────────────────────
interface ActiveJob { repoId: string; jobId: string }

export default function DashboardPage() {
  const [repos,        setRepos]        = useState<RepositoryResponse[]>([]);
  const [loading,      setLoading]      = useState(true);
  const [activeJob,    setActiveJob]    = useState<ActiveJob | null>(null);
  const [deleteTarget, setDeleteTarget] = useState<RepositoryResponse | null>(null);
  const [deleting,     setDeleting]     = useState(false);
  const [reindexingId, setReindexingId] = useState<string | null>(null);
  const [showForm,     setShowForm]     = useState(false);
  const { showError } = useError();

  const fetchRepos = useCallback(async () => {
    setLoading(true);
    try { setRepos(await listRepositories()); } catch { /* ok */ }
    finally { setLoading(false); }
  }, []);

  useEffect(() => { fetchRepos(); }, [fetchRepos]);

  const handleIndexingStarted = (repoId: string, jobId: string) => {
    setActiveJob({ repoId, jobId });
    setShowForm(false);
    fetchRepos();
  };
  const handleJobDone = () => { fetchRepos(); setTimeout(() => setActiveJob(null), 3000); };

  const handleDeleteConfirm = async () => {
    if (!deleteTarget) return;
    setDeleting(true);
    try {
      await deleteRepository(deleteTarget.id);
      if (activeJob?.repoId === deleteTarget.id) setActiveJob(null);
      setDeleteTarget(null);
      await fetchRepos();
    } catch (e: unknown) {
      showError("Delete failed", e instanceof Error ? e.message.replace(/^\d{3}\s?/, "") : "Could not delete repository.");
    } finally { setDeleting(false); }
  };

  const handleReindex = async (repo: RepositoryResponse) => {
    setReindexingId(repo.id);
    try {
      const r = await triggerReindex(repo.id);
      setActiveJob({ repoId: repo.id, jobId: r.job_id });
      await fetchRepos();
    } catch (e: unknown) {
      showError("Re-index failed", e instanceof Error ? e.message.replace(/^\d{3}\s?/, "") : "Could not trigger re-indexing.");
    } finally { setReindexingId(null); }
  };

  const indexed = repos.filter(r => r.status === "indexed").length;
  const failed  = repos.filter(r => ["failed", "error"].includes(r.status)).length;
  const active  = repos.filter(r => ["indexing", "queued", "pending"].includes(r.status)).length;

  return (
    <div className={PAGE}>
      <div className={INNER}>

        {/* ── Page header ───────────────────────────────────────────────── */}
        <div className="flex items-center justify-between">
          <div>
            <h1 className="text-2xl font-black text-slate-900 flex items-center gap-2.5 tracking-tight">
              <div className="bg-blue-600 p-2 rounded-xl">
                <LayoutGrid className="w-5 h-5 text-white" />
              </div>
              Dashboard
            </h1>
            <p className="text-slate-500 text-sm mt-1.5 ml-0.5">
              Index GitHub repositories and ask questions about your code.
            </p>
          </div>
          <div className="flex items-center gap-2">
            <button
              onClick={fetchRepos}
              disabled={loading}
              title="Refresh"
              className="p-2.5 rounded-xl border border-slate-200 bg-white text-slate-400 hover:text-blue-600 hover:border-blue-200 transition disabled:opacity-40 shadow-sm"
            >
              <RefreshCw className={`w-4 h-4 ${loading ? "animate-spin" : ""}`} />
            </button>
            <button
              onClick={() => setShowForm(v => !v)}
              className="flex items-center gap-2 px-4 py-2.5 bg-blue-600 hover:bg-blue-700 text-white text-sm font-bold rounded-xl transition shadow-sm shadow-blue-200"
            >
              <Plus className="w-4 h-4" />
              Add Repository
            </button>
          </div>
        </div>

        {/* ── Stats grid ────────────────────────────────────────────────── */}
        <div className="grid grid-cols-2 sm:grid-cols-4 gap-4">
          <StatCard label="Total"   value={repos.length} icon={GitBranch}    colorCls="text-blue-600"    bgCls="bg-blue-50 ring-1 ring-blue-100"    />
          <StatCard label="Indexed" value={indexed}       icon={CheckCircle2} colorCls="text-emerald-600" bgCls="bg-emerald-50 ring-1 ring-emerald-100"/>
          <StatCard label="Active"  value={active}        icon={Clock}        colorCls="text-amber-600"   bgCls="bg-amber-50 ring-1 ring-amber-100"   />
          <StatCard label="Failed"  value={failed}        icon={XCircle}      colorCls="text-red-600"     bgCls="bg-red-50 ring-1 ring-red-100"       />
        </div>

        {/* ── Add repo form (slide in/out) ───────────────────────────────── */}
        {showForm && (
          <div className={`${CARD} p-6`}>
            <div className="flex items-center justify-between mb-4">
              <h2 className="text-base font-bold text-slate-900">Index a Repository</h2>
              <button
                onClick={() => setShowForm(false)}
                className="text-slate-400 hover:text-slate-600 transition text-xs"
              >
                ✕ Close
              </button>
            </div>
            <RepoForm onIndexingStarted={handleIndexingStarted} />
          </div>
        )}

        {/* ── Active indexing job ────────────────────────────────────────── */}
        {activeJob && (
          <div>
            <p className={`${SECT_TITLE} mb-3`}>Active Indexing Job</p>
            <IndexingProgress repoId={activeJob.repoId} jobId={activeJob.jobId} onDone={handleJobDone} />
          </div>
        )}

        {/* ── Repository list ────────────────────────────────────────────── */}
        <div>
          <div className="flex items-center justify-between mb-4">
            <p className={SECT_TITLE}>
              Repositories{repos.length > 0 ? ` · ${repos.length}` : ""}
            </p>
            {repos.length > 0 && !showForm && (
              <button
                onClick={() => setShowForm(true)}
                className="flex items-center gap-1 text-xs text-blue-600 hover:text-blue-700 font-semibold transition"
              >
                <Plus className="w-3.5 h-3.5" /> Add new
              </button>
            )}
          </div>

          {loading ? (
            <div className="space-y-3">
              {[1, 2, 3].map(i => (
                <div key={i} className="bg-slate-100 rounded-2xl h-[72px] animate-pulse" />
              ))}
            </div>
          ) : repos.length === 0 ? (
            <div
              className={`${CARD} text-center py-16 border-2 border-dashed border-slate-200 shadow-none`}
            >
              <div className="bg-slate-100 w-14 h-14 rounded-2xl flex items-center justify-center mx-auto mb-4">
                <GitBranch className="w-7 h-7 text-slate-400" />
              </div>
              <p className="text-sm font-bold text-slate-700">No repositories yet</p>
              <p className="text-xs text-slate-400 mt-1 mb-5">Index your first GitHub repo to start asking questions.</p>
              <button
                onClick={() => setShowForm(true)}
                className="inline-flex items-center gap-2 px-5 py-2.5 bg-blue-600 hover:bg-blue-700 text-white text-sm font-bold rounded-xl transition"
              >
                <Plus className="w-4 h-4" /> Index a Repository
              </button>
            </div>
          ) : (
            <div className="space-y-2.5">
              {repos.map(r => (
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

        {/* ── Quick navigation to QA ─────────────────────────────────────── */}
        {indexed > 0 && (
          <a
            href="/qa"
            className={`${CARD} flex items-center justify-between px-6 py-4 hover:border-blue-200 hover:shadow-md transition group`}
          >
            <div>
              <p className="text-sm font-bold text-slate-900">Ready to ask questions?</p>
              <p className="text-xs text-slate-500 mt-0.5">
                {indexed} repositor{indexed !== 1 ? "ies" : "y"} indexed and ready.
              </p>
            </div>
            <div className="flex items-center gap-2 text-blue-600 font-semibold text-sm">
              Go to Q&A
              <ChevronRight className="w-4 h-4 group-hover:translate-x-0.5 transition-transform" />
            </div>
          </a>
        )}
      </div>

      {/* Delete modal */}
      {deleteTarget && (
        <DeleteModal
          repo={deleteTarget}
          onConfirm={handleDeleteConfirm}
          onCancel={() => setDeleteTarget(null)}
          busy={deleting}
        />
      )}
    </div>
  );
}
