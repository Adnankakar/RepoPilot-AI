import React, { useCallback, useEffect, useState } from "react";
import { listRepositories, RepositoryResponse } from "../api";
import RepoForm from "../components/RepoForm";
import IndexingProgress from "../components/IndexingProgress";
import { GitBranch, Database, CheckCircle2, Clock, XCircle, RefreshCw } from "lucide-react";

interface ActiveJob {
  repoId: string;
  jobId: string;
}

function StatusBadge({ status }: { status: string }) {
  const map: Record<string, string> = {
    pending: "bg-gray-100 text-gray-600",
    indexing: "bg-blue-100 text-blue-700",
    indexed: "bg-green-100 text-green-700",
    failed: "bg-red-100 text-red-700",
    error: "bg-red-100 text-red-700",
  };
  const cls = map[status] ?? "bg-gray-100 text-gray-500";
  return (
    <span className={`text-xs font-medium px-2.5 py-0.5 rounded-full capitalize ${cls}`}>
      {status}
    </span>
  );
}

function RepoCard({ repo }: { repo: RepositoryResponse }) {
  const icon =
    repo.status === "indexed" ? (
      <CheckCircle2 className="w-4 h-4 text-green-500" />
    ) : repo.status === "failed" || repo.status === "error" ? (
      <XCircle className="w-4 h-4 text-red-500" />
    ) : (
      <Clock className="w-4 h-4 text-blue-500" />
    );

  return (
    <div className="flex items-center justify-between bg-white border border-gray-200 rounded-xl px-5 py-4 shadow-sm">
      <div className="flex items-center gap-3 min-w-0">
        {icon}
        <div className="min-w-0">
          <p className="text-sm font-medium text-gray-800 truncate">{repo.url}</p>
          <p className="text-xs text-gray-400 mt-0.5">
            {repo.provider} · branch {repo.default_branch} ·{" "}
            {new Date(repo.created_at).toLocaleDateString()}
          </p>
        </div>
      </div>
      <StatusBadge status={repo.status} />
    </div>
  );
}

export default function DashboardPage() {
  const [repos, setRepos] = useState<RepositoryResponse[]>([]);
  const [loading, setLoading] = useState(true);
  const [activeJob, setActiveJob] = useState<ActiveJob | null>(null);

  const fetchRepos = useCallback(async () => {
    setLoading(true);
    try {
      const data = await listRepositories();
      setRepos(data);
    } catch {
      /* non-fatal */
    } finally {
      setLoading(false);
    }
  }, []);

  useEffect(() => {
    fetchRepos();
  }, [fetchRepos]);

  const handleIndexingStarted = (repoId: string, jobId: string) => {
    setActiveJob({ repoId, jobId });
    fetchRepos();
  };

  const handleJobDone = () => {
    fetchRepos();
    setTimeout(() => setActiveJob(null), 3000);
  };

  const indexed = repos.filter((r) => r.status === "indexed").length;
  const failed = repos.filter((r) => r.status === "failed" || r.status === "error").length;
  const pending = repos.filter((r) => r.status !== "indexed" && r.status !== "failed" && r.status !== "error").length;

  return (
    <div className="p-8 max-w-4xl mx-auto space-y-8">
      {/* Page header */}
      <div>
        <h1 className="text-2xl font-bold text-gray-900 flex items-center gap-2">
          <Database className="w-6 h-6 text-blue-600" />
          Dashboard
        </h1>
        <p className="text-gray-500 text-sm mt-1">
          Index GitHub repositories and monitor their status.
        </p>
      </div>

      {/* Stats */}
      <div className="grid grid-cols-3 gap-4">
        {[
          { label: "Total Repos", value: repos.length, icon: GitBranch, color: "text-gray-600" },
          { label: "Indexed", value: indexed, icon: CheckCircle2, color: "text-green-600" },
          { label: "Failed", value: failed, icon: XCircle, color: "text-red-500" },
        ].map(({ label, value, icon: Icon, color }) => (
          <div key={label} className="bg-white border border-gray-200 rounded-xl px-6 py-5 shadow-sm">
            <div className="flex items-center justify-between">
              <p className="text-sm text-gray-500">{label}</p>
              <Icon className={`w-5 h-5 ${color}`} />
            </div>
            <p className="text-3xl font-bold text-gray-900 mt-2">{value}</p>
          </div>
        ))}
      </div>

      {/* Add repository */}
      <div className="bg-white rounded-2xl border border-gray-200 shadow-sm p-6 space-y-4">
        <h2 className="text-base font-semibold text-gray-800">Index a Repository</h2>
        <RepoForm onIndexingStarted={handleIndexingStarted} />
      </div>

      {/* Active job progress */}
      {activeJob && (
        <div>
          <h2 className="text-base font-semibold text-gray-800 mb-3">Active Indexing Job</h2>
          <IndexingProgress
            repoId={activeJob.repoId}
            jobId={activeJob.jobId}
            onDone={handleJobDone}
          />
        </div>
      )}

      {/* Repository list */}
      <div>
        <div className="flex items-center justify-between mb-3">
          <h2 className="text-base font-semibold text-gray-800">
            Repositories{repos.length > 0 ? ` (${repos.length})` : ""}
          </h2>
          <button
            onClick={fetchRepos}
            className="flex items-center gap-1.5 text-xs text-gray-500 hover:text-blue-600 transition"
          >
            <RefreshCw className="w-3.5 h-3.5" /> Refresh
          </button>
        </div>

        {loading ? (
          <div className="space-y-3">
            {[1, 2, 3].map((i) => (
              <div key={i} className="bg-gray-100 rounded-xl h-16 animate-pulse" />
            ))}
          </div>
        ) : repos.length === 0 ? (
          <div className="text-center py-16 text-gray-400">
            <GitBranch className="w-10 h-10 mx-auto mb-3 opacity-30" />
            <p className="text-sm">No repositories yet. Add one above.</p>
          </div>
        ) : (
          <div className="space-y-3">
            {repos.map((r) => (
              <RepoCard key={r.id} repo={r} />
            ))}
          </div>
        )}
      </div>
    </div>
  );
}
