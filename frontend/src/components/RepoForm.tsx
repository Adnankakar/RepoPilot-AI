import React, { useState } from "react";
import { registerRepository } from "../api";
import { useError } from "../context/ErrorContext";
import { Loader2, CheckCircle2, GitFork } from "lucide-react";

interface Props {
  onIndexingStarted: (repoId: string, jobId: string) => void;
}

const GITHUB_RE = /^https?:\/\/(www\.)?github\.com\/[^/\s]+\/[^/\s]+(\/.*)?$/i;

export default function RepoForm({ onIndexingStarted }: Props) {
  const [url, setUrl]         = useState("");
  const [loading, setLoading] = useState(false);
  const [success, setSuccess] = useState<string | null>(null);
  const { showError } = useError();

  const submit = async (e: React.FormEvent) => {
    e.preventDefault();
    setSuccess(null);
    const trimmed = url.trim();
    if (!GITHUB_RE.test(trimmed)) {
      showError("Invalid repository URL", "Please enter a valid GitHub URL — https://github.com/owner/repo");
      return;
    }
    setLoading(true);
    try {
      const resp = await registerRepository(trimmed);
      setSuccess(`Queued! Job ${resp.job_id}`);
      setUrl("");
      onIndexingStarted(resp.repository.id, resp.job_id);
    } catch (err: unknown) {
      showError("Registration failed", err instanceof Error ? err.message.replace(/^\d{3}\s?/, "") : "Failed to register repository.");
    } finally {
      setLoading(false);
    }
  };

  return (
    <form onSubmit={submit} className="space-y-3">
      <div className="flex gap-3">
        <div className="relative flex-1">
          <GitFork className="absolute left-3 top-1/2 -translate-y-1/2 w-4 h-4 text-slate-400 pointer-events-none" />
          <input
            type="url"
            value={url}
            onChange={(e) => setUrl(e.target.value)}
            placeholder="https://github.com/owner/repository"
            required
            className="w-full pl-10 pr-4 py-2.5 border border-slate-200 rounded-xl bg-white text-sm text-slate-900 focus:outline-none focus:ring-2 focus:ring-blue-500 focus:border-transparent placeholder-slate-400 transition"
          />
        </div>
        <button
          type="submit"
          disabled={loading}
          className="flex items-center gap-2 px-5 py-2.5 bg-blue-600 hover:bg-blue-700 text-white text-sm font-semibold rounded-xl transition disabled:opacity-60 whitespace-nowrap"
        >
          {loading ? <Loader2 className="w-4 h-4 animate-spin" /> : null}
          {loading ? "Indexing…" : "Index Repo"}
        </button>
      </div>

      {success && (
        <div className="flex items-start gap-2 text-sm text-emerald-700 bg-emerald-50 border border-emerald-200 rounded-xl px-4 py-3">
          <CheckCircle2 className="w-4 h-4 mt-0.5 shrink-0 text-emerald-500" />
          {success}
        </div>
      )}
    </form>
  );
}
