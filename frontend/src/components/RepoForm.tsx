import React, { useState } from "react";
import { registerRepository } from "../api";
import { Loader2, CheckCircle2, AlertCircle, GitFork } from "lucide-react";

interface Props {
  onIndexingStarted: (repoId: string, jobId: string) => void;
}

const GITHUB_RE = /^https?:\/\/(www\.)?github\.com\/[^/\s]+\/[^/\s]+(\/.*)?$/i;

export default function RepoForm({ onIndexingStarted }: Props) {
  const [url, setUrl] = useState("");
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [success, setSuccess] = useState<string | null>(null);

  const submit = async (e: React.FormEvent) => {
    e.preventDefault();
    setError(null);
    setSuccess(null);

    const trimmed = url.trim();
    if (!GITHUB_RE.test(trimmed)) {
      setError("Please enter a valid GitHub repository URL (https://github.com/owner/repo).");
      return;
    }

    setLoading(true);
    try {
      const resp = await registerRepository(trimmed);
      setSuccess(`Repository queued! Job ID: ${resp.job_id}`);
      setUrl("");
      onIndexingStarted(resp.repository.id, resp.job_id);
    } catch (err: unknown) {
      setError(err instanceof Error ? err.message : "Failed to register repository.");
    } finally {
      setLoading(false);
    }
  };

  return (
    <form onSubmit={submit} className="space-y-4">
      <div>
        <label className="block text-sm font-medium text-gray-700 mb-1.5">
          GitHub Repository URL
        </label>
        <div className="flex gap-3">
          <div className="relative flex-1">
            <GitFork className="absolute left-3 top-1/2 -translate-y-1/2 w-4 h-4 text-gray-400 pointer-events-none" />
            <input
              type="url"
              value={url}
              onChange={(e) => setUrl(e.target.value)}
              placeholder="https://github.com/owner/repository"
              required
              className="w-full pl-10 pr-4 py-2.5 border border-gray-200 rounded-lg bg-white text-sm focus:outline-none focus:ring-2 focus:ring-blue-500 focus:border-transparent placeholder-gray-400"
            />
          </div>
          <button
            type="submit"
            disabled={loading}
            className="flex items-center gap-2 px-5 py-2.5 bg-blue-600 hover:bg-blue-700 text-white text-sm font-medium rounded-lg transition disabled:opacity-60 whitespace-nowrap"
          >
            {loading ? (
              <Loader2 className="w-4 h-4 animate-spin" />
            ) : null}
            {loading ? "Indexing…" : "Index Repository"}
          </button>
        </div>
      </div>

      {error && (
        <div className="flex items-start gap-2 text-sm text-red-700 bg-red-50 border border-red-200 rounded-lg px-4 py-3">
          <AlertCircle className="w-4 h-4 mt-0.5 shrink-0" />
          {error}
        </div>
      )}
      {success && (
        <div className="flex items-start gap-2 text-sm text-green-700 bg-green-50 border border-green-200 rounded-lg px-4 py-3">
          <CheckCircle2 className="w-4 h-4 mt-0.5 shrink-0" />
          {success}
        </div>
      )}
    </form>
  );
}
