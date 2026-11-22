import React, { useEffect, useRef, useState } from "react";
import {
  listRepositories,
  askQuestion,
  queryRetrieval,
  RepositoryResponse,
  ChatAskResponse,
  RetrievalResponse,
} from "../api";
import EvidencePanel from "../components/EvidencePanel";
import {
  Loader2,
  Send,
  AlertCircle,
  Info,
  CheckCircle2,
  MessageSquare,
  Bot,
  Code2,
  WifiOff,
  ServerCrash,
  ShieldAlert,
  SlidersHorizontal,
  ChevronDown,
  ChevronUp,
  Trash2,
} from "lucide-react";

// ─── Types ─────────────────────────────────────────────────────────���──────────

interface ConversationEntry {
  id: number;
  question: string;
  chatResult: ChatAskResponse;
  retrievalResult: RetrievalResponse | null;
}

// ─── Error classifier ─────────────────────────────────────────────────────────

interface ClassifiedError {
  icon: React.ReactNode;
  title: string;
  detail: string;
}

function classifyError(err: unknown): ClassifiedError {
  const msg = err instanceof Error ? err.message : String(err);
  const lower = msg.toLowerCase();

  if (lower.includes("401") || lower.includes("unauthorized") || lower.includes("not authenticated")) {
    return {
      icon: <ShieldAlert className="w-4 h-4 shrink-0 text-red-500" />,
      title: "Authentication error",
      detail: "Your session may have expired. Please log out and sign in again.",
    };
  }
  if (lower.includes("403") || lower.includes("forbidden") || lower.includes("not authorized")) {
    return {
      icon: <ShieldAlert className="w-4 h-4 shrink-0 text-red-500" />,
      title: "Access denied",
      detail: msg.replace(/^\d{3}\s?/, ""),
    };
  }
  if (lower.includes("409") || lower.includes("dimension mismatch") || lower.includes("mismatch")) {
    return {
      icon: <ServerCrash className="w-4 h-4 shrink-0 text-orange-500" />,
      title: "Embedding model mismatch",
      detail: msg.replace(/^\d{3}\s?/, ""),
    };
  }
  if (lower.includes("503") || lower.includes("unavailable") || lower.includes("provider")) {
    return {
      icon: <WifiOff className="w-4 h-4 shrink-0 text-orange-500" />,
      title: "LLM provider unavailable",
      detail: "The language model is temporarily unavailable. Try again in a moment.",
    };
  }
  if (lower.includes("500") || lower.includes("internal")) {
    return {
      icon: <ServerCrash className="w-4 h-4 shrink-0 text-red-500" />,
      title: "Server error",
      detail: "An internal server error occurred. Check the backend logs.",
    };
  }
  if (lower.includes("embedding") || lower.includes("retrieval failed")) {
    return {
      icon: <ServerCrash className="w-4 h-4 shrink-0 text-red-500" />,
      title: "Retrieval error",
      detail: msg.replace(/^\d{3}\s?/, ""),
    };
  }
  if (lower.includes("failed to fetch") || lower.includes("networkerror") || lower.includes("network")) {
    return {
      icon: <WifiOff className="w-4 h-4 shrink-0 text-orange-500" />,
      title: "Network error",
      detail: "Could not reach the server. Check that the backend is running.",
    };
  }
  return {
    icon: <AlertCircle className="w-4 h-4 shrink-0 text-red-500" />,
    title: "Unexpected error",
    detail: msg.replace(/^\d{3}\s?/, ""),
  };
}

// ─── Answer renderer ──────────────────────────────────────────────────────────
// Lightweight inline-code and bold rendering without a full markdown library.

function AnswerText({ text }: { text: string }) {
  // Split by fenced code blocks ```...```
  const parts = text.split(/(```[\s\S]*?```)/g);
  return (
    <div className="space-y-3 text-sm text-gray-800 leading-relaxed">
      {parts.map((part, i) => {
        if (part.startsWith("```")) {
          const inner = part.replace(/^```[^\n]*\n?/, "").replace(/```$/, "");
          return (
            <pre
              key={i}
              style={{
                backgroundColor: "#f8fafc",
                color: "#1e293b",
                borderLeft: "3px solid #3b82f6",
                fontFamily: "'Fira Code', 'Cascadia Code', Consolas, monospace",
                fontSize: "0.8rem",
                lineHeight: 1.6,
                padding: "0.75rem 1rem",
                borderRadius: "0 6px 6px 0",
                overflowX: "auto",
                whiteSpace: "pre",
                margin: 0,
              }}
            >
              {inner.trim()}
            </pre>
          );
        }
        // Inline: render **bold** and `code` spans
        const spans = part.split(/(\*\*[^*]+\*\*|`[^`]+`)/g);
        return (
          <p key={i} className="whitespace-pre-wrap">
            {spans.map((span, j) => {
              if (span.startsWith("**") && span.endsWith("**"))
                return <strong key={j}>{span.slice(2, -2)}</strong>;
              if (span.startsWith("`") && span.endsWith("`"))
                return (
                  <code
                    key={j}
                    className="bg-slate-100 text-slate-800 px-1 py-0.5 rounded text-xs font-mono"
                  >
                    {span.slice(1, -1)}
                  </code>
                );
              return <React.Fragment key={j}>{span}</React.Fragment>;
            })}
          </p>
        );
      })}
    </div>
  );
}

// ─── Component ────────────────────────────────────────────────────────────────

export default function QAPage() {
  const [repos, setRepos]           = useState<RepositoryResponse[]>([]);
  const [reposLoading, setReposLoading] = useState(true);
  const [reposError, setReposError] = useState<string | null>(null);

  const [selectedRepoId, setSelectedRepoId] = useState("");
  const [question, setQuestion]     = useState("");
  const [topK, setTopK]             = useState(5);
  const [similarityThreshold, setSimilarityThreshold] = useState(0.25);
  const [showAdvanced, setShowAdvanced] = useState(false);

  const [loading, setLoading]       = useState(false);
  const [error, setError]           = useState<ClassifiedError | null>(null);

  const [history, setHistory]       = useState<ConversationEntry[]>([]);
  const [currentId, setCurrentId]   = useState<number | null>(null);
  const entryCounter                = useRef(0);

  const answerRef = useRef<HTMLDivElement>(null);
  const textareaRef = useRef<HTMLTextAreaElement>(null);

  const current = history.find((h) => h.id === currentId) ?? null;

  useEffect(() => {
    listRepositories()
      .then((r) => {
        setRepos(r);
        if (r.length > 0) setSelectedRepoId(r[0].id);
      })
      .catch((e: unknown) => setReposError(classifyError(e).detail))
      .finally(() => setReposLoading(false));
  }, []);

  useEffect(() => {
    if (current && answerRef.current) {
      answerRef.current.scrollIntoView({ behavior: "smooth", block: "start" });
    }
  }, [currentId]);

  const performQuery = async (q: string) => {
    if (!q.trim()) return;
    setError(null);
    setLoading(true);

    try {
      const repoIdArg = selectedRepoId || undefined;
      const [chatResult, retrievalResult] = await Promise.allSettled([
        askQuestion(q.trim(), repoIdArg, topK, similarityThreshold),
        queryRetrieval(q.trim(), repoIdArg, topK, similarityThreshold),
      ]);

      if (chatResult.status === "rejected") {
        throw chatResult.reason;
      }

      const id = ++entryCounter.current;
      const entry: ConversationEntry = {
        id,
        question: q.trim(),
        chatResult: chatResult.value,
        retrievalResult: retrievalResult.status === "fulfilled" ? retrievalResult.value : null,
      };
      setHistory((h) => [entry, ...h]);
      setCurrentId(id);
    } catch (err: unknown) {
      setError(classifyError(err));
    } finally {
      setLoading(false);
    }
  };

  const handleSubmit = async (e: React.FormEvent) => {
    e.preventDefault();
    await performQuery(question);
    setQuestion("");
  };

  const handleKeyDown = (e: React.KeyboardEvent<HTMLTextAreaElement>) => {
    if (e.key === "Enter" && (e.metaKey || e.ctrlKey)) {
      e.preventDefault();
      handleSubmit(e as unknown as React.FormEvent);
    }
  };

  const clearHistory = () => {
    setHistory([]);
    setCurrentId(null);
    setError(null);
  };

  return (
    <div className="p-6 md:p-8 max-w-4xl mx-auto space-y-6">

      {/* ── Header ─────────────────────────────────────────────────────── */}
      <div>
        <h1 className="text-2xl font-bold text-gray-900 flex items-center gap-2.5">
          <MessageSquare className="w-6 h-6 text-blue-600" />
          Repository Q&A
        </h1>
        <p className="text-gray-500 text-sm mt-1">
          Ask anything about your indexed code. The AI retrieves relevant chunks and generates a grounded answer.
        </p>
      </div>

      {/* ── Query form ──────────────────────────────────────────────────── */}
      <div className="bg-white rounded-2xl shadow-sm border border-gray-200 overflow-hidden">
        <div className="p-6 space-y-4">

          {/* Repository error banner */}
          {reposError && (
            <div className="text-sm text-red-700 bg-red-50 border border-red-200 rounded-lg px-4 py-3 flex items-start gap-2">
              <AlertCircle className="w-4 h-4 shrink-0 mt-0.5 text-red-500" />
              <span><strong>Could not load repositories:</strong> {reposError}</span>
            </div>
          )}

          <form onSubmit={handleSubmit} className="space-y-4">
            {/* Repository selector */}
            <div>
              <label className="block text-xs font-semibold text-gray-500 uppercase tracking-wide mb-2">
                Repository
              </label>
              {reposLoading ? (
                <div className="flex items-center gap-2 text-sm text-gray-400 py-2">
                  <Loader2 className="w-4 h-4 animate-spin" /> Loading…
                </div>
              ) : repos.length === 0 ? (
                <p className="text-sm text-amber-600">
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
                      {r.url.replace("https://github.com/", "")} ({r.status})
                    </option>
                  ))}
                </select>
              )}
            </div>

            {/* Question input */}
            <div>
              <label className="block text-xs font-semibold text-gray-500 uppercase tracking-wide mb-2">
                Question
                <span className="ml-2 text-gray-300 normal-case font-normal">⌘↵ to send</span>
              </label>
              <div className="flex gap-3 items-end">
                <textarea
                  ref={textareaRef}
                  rows={2}
                  value={question}
                  onChange={(e) => setQuestion(e.target.value)}
                  onKeyDown={handleKeyDown}
                  placeholder="e.g. How is JWT authentication implemented?"
                  required
                  className="flex-1 px-4 py-3 border border-gray-200 rounded-lg text-sm resize-none focus:outline-none focus:ring-2 focus:ring-blue-500 placeholder-gray-300"
                />
                <button
                  type="submit"
                  disabled={loading || repos.length === 0 || !question.trim()}
                  className="shrink-0 flex items-center gap-2 px-5 py-2.5 bg-blue-600 hover:bg-blue-700 text-white text-sm font-medium rounded-lg transition disabled:opacity-50"
                >
                  {loading ? <Loader2 className="w-4 h-4 animate-spin" /> : <Send className="w-4 h-4" />}
                  Ask
                </button>
              </div>
            </div>

            {/* Advanced controls toggle */}
            <div>
              <button
                type="button"
                onClick={() => setShowAdvanced((v) => !v)}
                className="flex items-center gap-1.5 text-xs text-gray-400 hover:text-gray-600 transition"
              >
                <SlidersHorizontal className="w-3.5 h-3.5" />
                Advanced settings
                {showAdvanced
                  ? <ChevronUp className="w-3 h-3" />
                  : <ChevronDown className="w-3 h-3" />}
              </button>

              {showAdvanced && (
                <div className="flex flex-wrap items-center gap-6 mt-3 pt-3 border-t border-gray-100">
                  <div className="flex items-center gap-2">
                    <label className="text-xs font-medium text-gray-600 whitespace-nowrap">
                      Top-K chunks
                    </label>
                    <input
                      type="number"
                      min={1}
                      max={20}
                      value={topK}
                      onChange={(e) => setTopK(Number(e.target.value))}
                      className="w-20 px-2.5 py-1.5 border border-gray-200 rounded-lg text-sm focus:outline-none focus:ring-2 focus:ring-blue-500"
                    />
                  </div>
                  <div className="flex items-center gap-2">
                    <label className="text-xs font-medium text-gray-600 whitespace-nowrap">
                      Similarity threshold
                    </label>
                    <input
                      type="number"
                      min={0}
                      max={1}
                      step={0.05}
                      value={similarityThreshold}
                      onChange={(e) => setSimilarityThreshold(Number(e.target.value))}
                      className="w-24 px-2.5 py-1.5 border border-gray-200 rounded-lg text-sm focus:outline-none focus:ring-2 focus:ring-blue-500"
                    />
                    <span className="text-xs text-gray-300">0.25 recommended</span>
                  </div>
                </div>
              )}
            </div>

            {/* Error display */}
            {error && (
              <div className="flex items-start gap-3 text-sm bg-red-50 border border-red-200 rounded-lg px-4 py-3">
                {error.icon}
                <div className="flex-1 min-w-0">
                  <p className="font-semibold text-red-800">{error.title}</p>
                  <p className="text-red-700 mt-0.5 text-xs leading-relaxed">{error.detail}</p>
                </div>
                <button
                  type="button"
                  onClick={() => setError(null)}
                  className="text-red-300 hover:text-red-500 shrink-0"
                >
                  ✕
                </button>
              </div>
            )}
          </form>
        </div>
      </div>

      {/* ── Current answer ──────────────────────────────────────────────── */}
      {current && (
        <div className="space-y-4" ref={answerRef}>

          {/* Evidence / no-evidence banner */}
          {current.chatResult.has_sufficient_evidence ? (
            <div className="flex items-center gap-2 text-sm text-emerald-700 bg-emerald-50 border border-emerald-200 rounded-lg px-4 py-2.5">
              <CheckCircle2 className="w-4 h-4 shrink-0" />
              <span>
                Found {current.chatResult.chunks_used} relevant chunk{current.chatResult.chunks_used !== 1 ? "s" : ""}
              </span>
              {current.chatResult.best_score !== null && (
                <span className="text-emerald-600">
                  · best match {(current.chatResult.best_score * 100).toFixed(0)}%
                </span>
              )}
              <span className="text-emerald-400 text-xs ml-auto">
                threshold {(current.chatResult.threshold * 100).toFixed(0)}%
              </span>
            </div>
          ) : (
            <div className="flex items-start gap-2 text-sm text-amber-700 bg-amber-50 border border-amber-200 rounded-lg px-4 py-3">
              <Info className="w-4 h-4 shrink-0 mt-0.5" />
              <div>
                <p className="font-medium">Insufficient evidence</p>
                <p className="text-amber-600 text-xs mt-0.5">
                  {current.chatResult.insufficient_evidence_reason ??
                    "No relevant code found above the similarity threshold."}
                </p>
              </div>
            </div>
          )}

          {/* ── LLM Answer ──────────────────────────────────────────────── */}
          {current.chatResult.answer && (
            <div className="bg-white border border-gray-200 rounded-2xl shadow-sm overflow-hidden">
              <div className="flex items-center gap-2 px-5 py-3 border-b border-gray-100 bg-blue-50">
                <Bot className="w-4 h-4 text-blue-600" />
                <span className="text-sm font-semibold text-blue-800">AI Answer</span>
                <span className="ml-auto text-xs text-blue-400 font-mono truncate max-w-xs">
                  {current.question}
                </span>
              </div>
              <div className="px-5 py-5">
                <AnswerText text={current.chatResult.answer} />
              </div>
            </div>
          )}

          {/* ── Code Evidence ────────────────────────────────────────────── */}
          {current.retrievalResult && current.retrievalResult.chunks.length > 0 && (
            <div className="bg-white border border-gray-200 rounded-2xl shadow-sm overflow-hidden">
              <div className="flex items-center gap-2 px-5 py-3 border-b border-gray-100 bg-gray-50">
                <Code2 className="w-4 h-4 text-gray-500" />
                <span className="text-sm font-semibold text-gray-600">Code Evidence</span>
                <span className="ml-auto text-xs text-gray-400">
                  {current.retrievalResult.chunks.length} chunk{current.retrievalResult.chunks.length !== 1 ? "s" : ""}
                </span>
              </div>
              <div className="p-5">
                <EvidencePanel chunks={current.retrievalResult.chunks} />
              </div>
            </div>
          )}

          {/* No evidence at all */}
          {!current.chatResult.answer &&
            (!current.retrievalResult || current.retrievalResult.chunks.length === 0) && (
              <div className="text-center py-10 text-gray-400 border border-dashed border-gray-200 rounded-2xl">
                <Code2 className="w-8 h-8 mx-auto mb-2 opacity-30" />
                <p className="text-sm">No matching code chunks found in the indexed repository.</p>
                <p className="text-xs mt-1 text-gray-300">
                  Try lowering the similarity threshold or re-phrasing your question.
                </p>
              </div>
            )}
        </div>
      )}

      {/* ── Conversation history ─────────────────────────────────────────── */}
      {history.length > 0 && (
        <div>
          <div className="flex items-center justify-between mb-3">
            <h2 className="text-xs font-semibold text-gray-400 uppercase tracking-widest">
              History ({history.length})
            </h2>
            <button
              onClick={clearHistory}
              className="flex items-center gap-1 text-xs text-gray-400 hover:text-red-500 transition"
            >
              <Trash2 className="w-3 h-3" /> Clear
            </button>
          </div>
          <div className="space-y-2">
            {history.map((entry) => (
              <button
                key={entry.id}
                onClick={() => setCurrentId(entry.id)}
                className={`w-full text-left px-4 py-3 rounded-xl text-sm transition border ${
                  entry.id === currentId
                    ? "border-blue-300 bg-blue-50 text-blue-800"
                    : "border-gray-200 bg-white text-gray-700 hover:border-gray-300 hover:bg-gray-50"
                }`}
              >
                <span className="line-clamp-1">{entry.question}</span>
                <span className="text-xs mt-0.5 block opacity-60">
                  {entry.chatResult.has_sufficient_evidence
                    ? `${entry.chatResult.chunks_used} chunk${entry.chatResult.chunks_used !== 1 ? "s" : ""} · ${entry.chatResult.answer ? "answered" : "no answer"}`
                    : "insufficient evidence"}
                </span>
              </button>
            ))}
          </div>
        </div>
      )}
    </div>
  );
}
