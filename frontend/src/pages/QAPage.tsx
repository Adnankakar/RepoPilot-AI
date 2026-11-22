import React, { useEffect, useState } from "react";
import { listRepositories, queryRetrieval, RepositoryResponse, RetrievalResponse } from "../api";
import EvidencePanel from "../components/EvidencePanel";
import {
  Loader2,
  Send,
  AlertCircle,
  Info,
  CheckCircle2,
  MessageSquare,
} from "lucide-react";

interface ConversationEntry {
  question: string;
  result: RetrievalResponse;
}

export default function QAPage() {
  const [repos, setRepos] = useState<RepositoryResponse[]>([]);
  const [reposLoading, setReposLoading] = useState(true);
  const [reposError, setReposError] = useState<string | null>(null);

  const [selectedRepoId, setSelectedRepoId] = useState<string>("");
  const [question, setQuestion] = useState("");
  const [topK, setTopK] = useState(5);
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [history, setHistory] = useState<ConversationEntry[]>([]);
  const [current, setCurrent] = useState<RetrievalResponse | null>(null);

  useEffect(() => {
    listRepositories()
      .then((r) => {
        setRepos(r);
        if (r.length > 0) setSelectedRepoId(r[0].id);
      })
      .catch((e: Error) => setReposError(e.message))
      .finally(() => setReposLoading(false));
  }, []);

  const ask = async (e: React.FormEvent) => {
    e.preventDefault();
    if (!question.trim()) return;
    setError(null);
    setLoading(true);
    try {
      const result = await queryRetrieval(
        question.trim(),
        selectedRepoId || undefined,
        topK
      );
      setHistory((h) => [{ question: question.trim(), result }, ...h]);
      setCurrent(result);
      setQuestion("");
    } catch (err: unknown) {
      setError(err instanceof Error ? err.message : "Query failed.");
    } finally {
      setLoading(false);
    }
  };

  return (
    <div className="p-8 max-w-4xl mx-auto space-y-8">
      {/* Header */}
      <div>
        <h1 className="text-2xl font-bold text-gray-900 flex items-center gap-2">
          <MessageSquare className="w-6 h-6 text-blue-600" />
          Repository Q&A
        </h1>
        <p className="text-gray-500 text-sm mt-1">
          Ask questions about indexed repositories. Results are ranked by vector similarity.
        </p>
      </div>

      {/* Query form */}
      <div className="bg-white rounded-2xl shadow-sm border border-gray-200 p-6 space-y-4">
        {reposError && (
          <div className="text-sm text-red-700 bg-red-50 border border-red-200 rounded-lg px-4 py-3 flex items-center gap-2">
            <AlertCircle className="w-4 h-4 shrink-0" /> {reposError}
          </div>
        )}

        <form onSubmit={ask} className="space-y-4">
          {/* Repository selector */}
          <div>
            <label className="block text-sm font-medium text-gray-700 mb-1.5">
              Repository
            </label>
            {reposLoading ? (
              <div className="flex items-center gap-2 text-sm text-gray-400">
                <Loader2 className="w-4 h-4 animate-spin" /> Loading repositories…
              </div>
            ) : repos.length === 0 ? (
              <p className="text-sm text-gray-400 italic">
                No repositories indexed yet. Go to the Dashboard to add one.
              </p>
            ) : (
              <select
                value={selectedRepoId}
                onChange={(e) => setSelectedRepoId(e.target.value)}
                className="w-full px-3 py-2.5 border border-gray-200 rounded-lg text-sm bg-white focus:outline-none focus:ring-2 focus:ring-blue-500"
              >
                <option value="">All repositories</option>
                {repos.map((r) => (
                  <option key={r.id} value={r.id}>
                    {r.url} ({r.status})
                  </option>
                ))}
              </select>
            )}
          </div>

          {/* Top-K */}
          <div className="flex items-center gap-4">
            <label className="text-sm font-medium text-gray-700 whitespace-nowrap">
              Results (top‑K)
            </label>
            <input
              type="number"
              min={1}
              max={50}
              value={topK}
              onChange={(e) => setTopK(Number(e.target.value))}
              className="w-20 px-3 py-1.5 border border-gray-200 rounded-lg text-sm focus:outline-none focus:ring-2 focus:ring-blue-500"
            />
          </div>

          {/* Question */}
          <div>
            <label className="block text-sm font-medium text-gray-700 mb-1.5">
              Question
            </label>
            <div className="flex gap-3">
              <textarea
                rows={2}
                value={question}
                onChange={(e) => setQuestion(e.target.value)}
                placeholder="e.g. How is JWT authentication implemented?"
                required
                className="flex-1 px-4 py-3 border border-gray-200 rounded-lg text-sm resize-none focus:outline-none focus:ring-2 focus:ring-blue-500 placeholder-gray-400"
              />
              <button
                type="submit"
                disabled={loading || repos.length === 0}
                className="self-end flex items-center gap-2 px-5 py-2.5 bg-blue-600 hover:bg-blue-700 text-white text-sm font-medium rounded-lg transition disabled:opacity-60"
              >
                {loading ? (
                  <Loader2 className="w-4 h-4 animate-spin" />
                ) : (
                  <Send className="w-4 h-4" />
                )}
                Ask
              </button>
            </div>
          </div>

          {error && (
            <div className="flex items-center gap-2 text-sm text-red-700 bg-red-50 border border-red-200 rounded-lg px-4 py-3">
              <AlertCircle className="w-4 h-4 shrink-0" /> {error}
            </div>
          )}
        </form>
      </div>

      {/* Current result */}
      {current && (
        <div className="space-y-6">
          {/* Evidence banner */}
          {current.has_sufficient_evidence ? (
            <div className="flex items-center gap-2 text-sm text-green-700 bg-green-50 border border-green-200 rounded-lg px-4 py-3">
              <CheckCircle2 className="w-4 h-4 shrink-0" />
              Sufficient evidence found (best score:{" "}
              {current.best_score !== null ? current.best_score.toFixed(4) : "—"}, threshold:{" "}
              {current.threshold})
            </div>
          ) : (
            <div className="flex items-center gap-2 text-sm text-amber-700 bg-amber-50 border border-amber-200 rounded-lg px-4 py-3">
              <Info className="w-4 h-4 shrink-0" />
              {current.insufficient_evidence_reason ?? "Insufficient evidence found in the indexed codebase."}
            </div>
          )}

          {/* Evidence panel */}
          {current.chunks.length > 0 ? (
            <EvidencePanel chunks={current.chunks} />
          ) : (
            <p className="text-sm text-gray-400 italic">No matching chunks returned.</p>
          )}
        </div>
      )}

      {/* Conversation history */}
      {history.length > 1 && (
        <div>
          <h2 className="text-sm font-semibold text-gray-500 uppercase tracking-wide mb-3">
            Previous questions
          </h2>
          <div className="space-y-2">
            {history.slice(1).map((entry, i) => (
              <button
                key={i}
                onClick={() => setCurrent(entry.result)}
                className="w-full text-left px-4 py-3 bg-white border border-gray-200 rounded-xl text-sm hover:border-blue-300 hover:bg-blue-50 transition"
              >
                <span className="text-gray-800">{entry.question}</span>
                <span className="ml-2 text-xs text-gray-400">
                  ({entry.result.chunks.length} chunk{entry.result.chunks.length !== 1 ? "s" : ""})
                </span>
              </button>
            ))}
          </div>
        </div>
      )}
    </div>
  );
}
