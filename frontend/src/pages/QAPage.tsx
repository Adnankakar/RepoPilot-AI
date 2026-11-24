import React, { useEffect, useRef, useState } from "react";
import { Light as SyntaxHighlighter } from "react-syntax-highlighter";
import { atomOneDark } from "react-syntax-highlighter/dist/esm/styles/hljs";
import python     from "react-syntax-highlighter/dist/esm/languages/hljs/python";
import typescript from "react-syntax-highlighter/dist/esm/languages/hljs/typescript";
import javascript from "react-syntax-highlighter/dist/esm/languages/hljs/javascript";
import bash       from "react-syntax-highlighter/dist/esm/languages/hljs/bash";
import sql        from "react-syntax-highlighter/dist/esm/languages/hljs/sql";
import {
  listRepositories, askQuestion, queryRetrieval,
  RepositoryResponse, ChatAskResponse, RetrievalResponse,
} from "../api";
import EvidencePanel from "../components/EvidencePanel";
import { useError } from "../context/ErrorContext";
import {
  Loader2, AlertCircle, Info, CheckCircle2,
  MessageSquare, Bot, Code2, WifiOff, ServerCrash,
  ShieldAlert, SlidersHorizontal, ChevronDown, ChevronUp,
  Trash2, Sparkles, Clock, User, Copy, Check,
  BookOpen, Lightbulb, Database, ChevronRight,
} from "lucide-react";

SyntaxHighlighter.registerLanguage("python",     python);
SyntaxHighlighter.registerLanguage("typescript", typescript);
SyntaxHighlighter.registerLanguage("javascript", javascript);
SyntaxHighlighter.registerLanguage("bash",       bash);
SyntaxHighlighter.registerLanguage("sql",        sql);

// ── Types ─────────────────────────────────────────────────────────────────────
interface Entry {
  id: number;
  question: string;
  chatResult: ChatAskResponse;
  retrievalResult: RetrievalResponse | null;
  ts: Date;
}
interface AppError { icon: React.ReactNode; title: string; detail: string; }

// ── Error classifier ──────────────────────────────────────────────────────────
function classify(err: unknown): AppError {
  const msg   = err instanceof Error ? err.message : String(err);
  const lower = msg.toLowerCase();
  if (lower.includes("401") || lower.includes("unauthorized"))
    return { icon: <ShieldAlert className="w-4 h-4 text-red-400 shrink-0" />, title: "Session expired", detail: "Please sign out and sign in again." };
  if (lower.includes("403") || lower.includes("forbidden"))
    return { icon: <ShieldAlert className="w-4 h-4 text-red-400 shrink-0" />, title: "Access denied", detail: msg.replace(/^\d{3}\s?/, "") };
  if (lower.includes("409") || lower.includes("mismatch"))
    return { icon: <ServerCrash className="w-4 h-4 text-orange-400 shrink-0" />, title: "Embedding model mismatch", detail: msg.replace(/^\d{3}\s?/, "") };
  if (lower.includes("503") || lower.includes("unavailable"))
    return { icon: <WifiOff className="w-4 h-4 text-orange-400 shrink-0" />, title: "LLM unavailable", detail: "The language model is temporarily down. Try again shortly." };
  if (lower.includes("500") || lower.includes("internal"))
    return { icon: <ServerCrash className="w-4 h-4 text-red-400 shrink-0" />, title: "Server error", detail: "An internal error occurred." };
  if (lower.includes("networkerror") || lower.includes("failed to fetch"))
    return { icon: <WifiOff className="w-4 h-4 text-orange-400 shrink-0" />, title: "Network error", detail: "Cannot reach the server. Is the backend running?" };
  return { icon: <AlertCircle className="w-4 h-4 text-red-400 shrink-0" />, title: "Error", detail: msg.replace(/^\d{3}\s?/, "") };
}

// ── Language detection ────────────────────────────────────────────────────────
function fenceLanguage(tag: string): string {
  const t = tag.trim().toLowerCase();
  if (!t) return "python";
  if (["py","python"].includes(t)) return "python";
  if (["ts","tsx","typescript"].includes(t)) return "typescript";
  if (["js","jsx","javascript"].includes(t)) return "javascript";
  if (["sh","bash","shell"].includes(t)) return "bash";
  if (["sql"].includes(t)) return "sql";
  return t;
}

// ── Copy button ───────────────────────────────────────────────────────────────
function CopyBtn({ text }: { text: string }) {
  const [copied, setCopied] = useState(false);
  return (
    <button
      onClick={() => { navigator.clipboard.writeText(text).then(() => { setCopied(true); setTimeout(() => setCopied(false), 1800); }); }}
      className="flex items-center gap-1.5 text-xs px-2.5 py-1 rounded-lg transition-colors"
      style={{ color: copied ? "#34d399" : "#94a3b8", background: "rgba(255,255,255,0.07)" }}
    >
      {copied ? <><Check className="w-3.5 h-3.5" />Copied</> : <><Copy className="w-3.5 h-3.5" />Copy</>}
    </button>
  );
}

// ── Rich Answer Renderer ──────────────────────────────────────────────────────
function AnswerText({ text }: { text: string }) {
  const parts = text.split(/(```[\s\S]*?```)/g);

  return (
    <div className="space-y-4">
      {parts.map((part, i) => {
        // ── Fenced code block (keep colors exactly as before) ──
        if (part.startsWith("```")) {
          const firstNewline = part.indexOf("\n");
          const tag  = firstNewline > 2 ? part.slice(3, firstNewline).trim() : "";
          const code = firstNewline > 2 ? part.slice(firstNewline + 1).replace(/```$/, "") : part.slice(3).replace(/```$/, "");
          const lang = fenceLanguage(tag);
          return (
            <div key={i} className="rounded-xl overflow-hidden border border-slate-700/50 shadow-md">
              <div className="flex items-center justify-between px-4 py-2" style={{ background: "#1e2433" }}>
                <div className="flex items-center gap-2">
                  <span className="flex gap-1.5">
                    <span className="w-2.5 h-2.5 rounded-full bg-red-500/70" />
                    <span className="w-2.5 h-2.5 rounded-full bg-yellow-500/70" />
                    <span className="w-2.5 h-2.5 rounded-full bg-green-500/70" />
                  </span>
                  <span className="text-xs font-mono px-2 py-0.5 rounded" style={{ background: "rgba(255,255,255,0.08)", color: "#94a3b8" }}>
                    {lang}
                  </span>
                </div>
                <CopyBtn text={code.trim()} />
              </div>
              <SyntaxHighlighter
                language={lang}
                style={atomOneDark}
                customStyle={{ margin: 0, padding: "1rem 1.25rem", background: "#1a1f2e", fontSize: "0.8rem", lineHeight: "1.65", borderRadius: 0 }}
                codeTagProps={{ style: { fontFamily: "'Fira Code','Cascadia Code',Consolas,monospace" } }}
              >
                {code.trim()}
              </SyntaxHighlighter>
            </div>
          );
        }

        if (!part.trim()) return null;

        // ── Prose renderer ──────────────────────────────────────────────────
        const lines = part.split("\n");
        const elements: React.ReactNode[] = [];
        let listBuf: string[] = [];
        let listType: "ul" | "ol" | null = null;

        const flushList = (key: string) => {
          if (!listBuf.length) return;
          if (listType === "ol") {
            elements.push(
              <ol key={key} className="list-none space-y-2 my-1 pl-1">
                {listBuf.map((item, n) => (
                  <li key={n} className="flex items-start gap-3">
                    <span className="shrink-0 w-5 h-5 rounded-full bg-violet-100 text-violet-700 text-xs font-bold flex items-center justify-center mt-0.5">
                      {n + 1}
                    </span>
                    <span className="text-slate-700 text-sm leading-relaxed">{renderInline(item)}</span>
                  </li>
                ))}
              </ol>
            );
          } else {
            elements.push(
              <ul key={key} className="list-none space-y-2 my-1 pl-1">
                {listBuf.map((item, n) => (
                  <li key={n} className="flex items-start gap-3">
                    <ChevronRight className="w-3.5 h-3.5 text-violet-400 shrink-0 mt-1" />
                    <span className="text-slate-700 text-sm leading-relaxed">{renderInline(item)}</span>
                  </li>
                ))}
              </ul>
            );
          }
          listBuf = [];
          listType = null;
        };

        lines.forEach((line, li) => {
          // Heading ## / ###
          const h2 = line.match(/^##\s+(.+)/);
          const h3 = line.match(/^###\s+(.+)/);
          if (h2) {
            flushList(`fl-${i}-${li}`);
            elements.push(
              <h2 key={`h2-${i}-${li}`} className="text-base font-bold text-slate-900 mt-5 mb-1 pb-1 border-b border-slate-100 flex items-center gap-2">
                <BookOpen className="w-4 h-4 text-violet-500 shrink-0" />
                {renderInline(h2[1])}
              </h2>
            );
            return;
          }
          if (h3) {
            flushList(`fl-${i}-${li}`);
            elements.push(
              <h3 key={`h3-${i}-${li}`} className="text-sm font-bold text-slate-800 mt-4 mb-0.5 flex items-center gap-1.5">
                <span className="w-1 h-4 rounded-full bg-violet-400 inline-block" />
                {renderInline(h3[1])}
              </h3>
            );
            return;
          }

          // Blockquote >
          const bq = line.match(/^>\s*(.*)/);
          if (bq) {
            flushList(`fl-${i}-${li}`);
            elements.push(
              <blockquote key={`bq-${i}-${li}`} className="border-l-4 border-violet-300 pl-4 py-1 my-1 bg-violet-50/60 rounded-r-lg">
                <p className="text-sm text-slate-600 italic leading-relaxed">{renderInline(bq[1])}</p>
              </blockquote>
            );
            return;
          }

          // Ordered list  1. / 2.
          const olMatch = line.match(/^\d+\.\s+(.*)/);
          if (olMatch) {
            if (listType === "ul") flushList(`fl-${i}-${li}`);
            listType = "ol";
            listBuf.push(olMatch[1]);
            return;
          }

          // Unordered list  - / * / •
          const ulMatch = line.match(/^[-*•]\s+(.*)/);
          if (ulMatch) {
            if (listType === "ol") flushList(`fl-${i}-${li}`);
            listType = "ul";
            listBuf.push(ulMatch[1]);
            return;
          }

          // Flush pending list before a normal line
          flushList(`fl-${i}-${li}`);

          // Horizontal rule
          if (/^---+$/.test(line.trim())) {
            elements.push(<hr key={`hr-${i}-${li}`} className="border-slate-200 my-3" />);
            return;
          }

          // Empty line → spacer
          if (!line.trim()) {
            elements.push(<div key={`sp-${i}-${li}`} className="h-1" />);
            return;
          }

          // Normal paragraph line
          elements.push(
            <p key={`p-${i}-${li}`} className="text-sm text-slate-700 leading-relaxed">
              {renderInline(line)}
            </p>
          );
        });

        flushList(`fl-end-${i}`);
        return <div key={i} className="space-y-1">{elements}</div>;
      })}
    </div>
  );
}

// ── Inline formatter: **bold**, *italic*, `code` ─────────────────────────────
function renderInline(text: string): React.ReactNode {
  const tokens = text.split(/(\*\*[^*]+\*\*|\*[^*]+\*|`[^`]+`)/g);
  return (
    <>
      {tokens.map((t, i) => {
        if (t.startsWith("**") && t.endsWith("**"))
          return <strong key={i} className="font-semibold text-slate-900">{t.slice(2, -2)}</strong>;
        if (t.startsWith("*") && t.endsWith("*"))
          return <em key={i} className="italic text-slate-600">{t.slice(1, -1)}</em>;
        if (t.startsWith("`") && t.endsWith("`"))
          return (
            <code key={i} className="bg-slate-100 text-violet-700 px-1.5 py-0.5 rounded-md text-xs font-mono border border-slate-200">
              {t.slice(1, -1)}
            </code>
          );
        return <React.Fragment key={i}>{t}</React.Fragment>;
      })}
    </>
  );
}

// ── Suggested questions ───────────────────────────────────────────────────────
const SUGGESTIONS = [
  "How is authentication implemented?",
  "Where are database models defined?",
  "How does the API routing work?",
  "What does the main entry point do?",
];

// ── Page ──────────────────────────────────────────────────────────────────────
export default function QAPage() {
  const [repos,     setRepos]     = useState<RepositoryResponse[]>([]);
  const [reposLoad, setReposLoad] = useState(true);
  const [repoId,    setRepoId]    = useState("");
  const [question,  setQuestion]  = useState("");
  const [topK,      setTopK]      = useState(5);
  const [threshold, setThreshold] = useState(0.25);
  const [advanced,  setAdvanced]  = useState(false);
  const [loading,   setLoading]   = useState(false);
  const [history,   setHistory]   = useState<Entry[]>([]);
  const [currentId, setCurrentId] = useState<number | null>(null);
  const [activeTab, setActiveTab] = useState<"answer" | "evidence">("answer");
  const counter    = useRef(0);
  const textareaRef = useRef<HTMLTextAreaElement>(null);
  const { showError } = useError();
  const current = history.find(h => h.id === currentId) ?? null;

  useEffect(() => {
    listRepositories()
      .then(r => { setRepos(r); if (r.length) setRepoId(r[0].id); })
      .catch(e => { const c = classify(e); showError(c.title, c.detail, c.icon); })
      .finally(() => setReposLoad(false));
  }, []);

  // Answer is now always visible (fixed-height layout), so no page scroll needed.
  useEffect(() => {
    if (current) setActiveTab("answer");
  }, [currentId]); // eslint-disable-line

  const ask = async (q: string) => {
    if (!q.trim()) return;
    setLoading(true);
    try {
      const rid = repoId || undefined;
      const [chat, retrieval] = await Promise.allSettled([
        askQuestion(q.trim(), rid, topK, threshold),
        queryRetrieval(q.trim(), rid, topK, threshold),
      ]);
      if (chat.status === "rejected") throw chat.reason;
      const id = ++counter.current;
      const entry: Entry = {
        id, question: q.trim(),
        chatResult: chat.value,
        retrievalResult: retrieval.status === "fulfilled" ? retrieval.value : null,
        ts: new Date(),
      };
      setHistory(h => [entry, ...h]);
      setCurrentId(id);
    } catch (e) {
      const c = classify(e);
      showError(c.title, c.detail, c.icon);
    } finally {
      setLoading(false);
    }
  };

  const onSubmit = async (e: React.FormEvent) => { e.preventDefault(); await ask(question); setQuestion(""); };
  const onKey = (e: React.KeyboardEvent<HTMLTextAreaElement>) => {
    if (e.key === "Enter" && (e.metaKey || e.ctrlKey)) { e.preventDefault(); onSubmit(e as unknown as React.FormEvent); }
  };

  const evidenceCount = current?.retrievalResult?.chunks.length ?? 0;

  return (
    // Fixed-height shell: the page itself never scrolls. The answer/evidence
    // card scrolls internally inside its own bounded region.
    <div className="h-screen overflow-hidden flex flex-col bg-slate-50">

      {/* ── Page header (fixed) ──────────────────────────────────────── */}
      <div className="max-w-6xl mx-auto w-full px-6 pt-6 pb-3 shrink-0 flex items-start justify-between">
        <div>
          <h1 className="text-2xl font-black text-slate-900 flex items-center gap-3 tracking-tight">
            <div className="bg-gradient-to-br from-violet-600 to-indigo-600 p-2.5 rounded-xl shadow-md shadow-violet-200">
              <MessageSquare className="w-5 h-5 text-white" />
            </div>
            Repository Q&amp;A
          </h1>
          <p className="text-slate-500 text-sm mt-1.5 ml-0.5">
            Ask questions in plain English — the AI retrieves relevant code and explains it.
          </p>
        </div>
        {history.length > 0 && (
          <button
            onClick={() => { setHistory([]); setCurrentId(null); }}
            className="flex items-center gap-1.5 text-xs text-slate-400 hover:text-red-500 transition px-3 py-1.5 rounded-lg hover:bg-red-50 border border-transparent hover:border-red-100"
          >
            <Trash2 className="w-3.5 h-3.5" /> Clear history
          </button>
        )}
      </div>

      {/* ── Main grid (fills remaining height, no page scroll) ──────── */}
      <div className="flex-1 min-h-0 max-w-6xl mx-auto w-full px-6 pb-6">
        <div className="grid grid-cols-1 lg:grid-cols-3 gap-6 h-full">

          {/* ── LEFT: query panel (scrolls internally if too tall) ───── */}
          <div className="lg:col-span-1 lg:h-full lg:min-h-0 lg:overflow-y-auto space-y-4">

            {/* Query card */}
            <div className="bg-white rounded-2xl border border-slate-200 shadow-sm overflow-hidden">
              {/* Card header */}
              <div className="px-5 py-4 border-b border-slate-100 bg-gradient-to-r from-slate-50 to-white">
                <p className="text-xs font-bold text-slate-500 uppercase tracking-widest flex items-center gap-2">
                  <Sparkles className="w-3.5 h-3.5 text-violet-500" />
                  Ask a Question
                </p>
              </div>

              <div className="p-5 space-y-4">
                <form onSubmit={onSubmit} className="space-y-4">
                  {/* Repository selector */}
                  <div>
                    <label className="block text-xs font-semibold text-slate-500 uppercase tracking-wide mb-1.5">
                      Repository
                    </label>
                    {reposLoad ? (
                      <div className="flex items-center gap-2 text-sm text-slate-400 py-1.5">
                        <Loader2 className="w-4 h-4 animate-spin text-violet-500" /> Loading…
                      </div>
                    ) : repos.length === 0 ? (
                      <p className="text-xs text-amber-600 bg-amber-50 border border-amber-200 rounded-xl px-3 py-2.5">
                        No repositories indexed yet.{" "}
                        <a href="/dashboard" className="text-violet-600 hover:underline font-semibold">Go to Dashboard</a>
                        {" "}to add one.
                      </p>
                    ) : (
                      <div className="relative">
                        <Database className="w-3.5 h-3.5 text-slate-400 absolute left-3 top-1/2 -translate-y-1/2 pointer-events-none" />
                        <select
                          value={repoId}
                          onChange={e => setRepoId(e.target.value)}
                          className="w-full pl-8 pr-3.5 py-2.5 border border-slate-200 rounded-xl text-sm bg-white text-slate-900 focus:outline-none focus:ring-2 focus:ring-violet-500 transition appearance-none"
                        >
                          <option value="">All repositories</option>
                          {repos.map(r => (
                            <option key={r.id} value={r.id}>
                              {r.url.replace("https://github.com/", "")} ({r.status})
                            </option>
                          ))}
                        </select>
                      </div>
                    )}
                  </div>

                  {/* Textarea */}
                  <div>
                    <label className="block text-xs font-semibold text-slate-500 uppercase tracking-wide mb-1.5">
                      Your Question
                      <span className="normal-case font-normal text-slate-300 ml-2">Ctrl+Enter to send</span>
                    </label>
                    <textarea
                      ref={textareaRef}
                      rows={4}
                      value={question}
                      onChange={e => setQuestion(e.target.value)}
                      onKeyDown={onKey}
                      placeholder="e.g. How is JWT authentication implemented?"
                      required
                      className="w-full px-4 py-3 border border-slate-200 rounded-xl text-sm text-slate-900 resize-none focus:outline-none focus:ring-2 focus:ring-violet-500 placeholder-slate-300 transition leading-relaxed"
                    />
                  </div>

                  {/* Submit */}
                  <button
                    type="submit"
                    disabled={loading || repos.length === 0 || !question.trim()}
                    className="w-full flex items-center justify-center gap-2 py-3 bg-gradient-to-r from-violet-600 to-indigo-600 hover:from-violet-700 hover:to-indigo-700 text-white text-sm font-bold rounded-xl transition disabled:opacity-50 shadow-md shadow-violet-200 active:scale-[0.98]"
                  >
                    {loading
                      ? <><Loader2 className="w-4 h-4 animate-spin" /> Thinking…</>
                      : <><Sparkles className="w-4 h-4" /> Ask AI</>}
                  </button>

                  {/* Advanced toggle */}
                  <div>
                    <button
                      type="button"
                      onClick={() => setAdvanced(v => !v)}
                      className="flex items-center gap-1.5 text-xs text-slate-400 hover:text-slate-600 transition"
                    >
                      <SlidersHorizontal className="w-3.5 h-3.5" />
                      Advanced settings
                      {advanced ? <ChevronUp className="w-3 h-3" /> : <ChevronDown className="w-3 h-3" />}
                    </button>
                    {advanced && (
                      <div className="flex flex-wrap gap-4 mt-3 pt-3 border-t border-slate-100">
                        <div className="flex items-center gap-2">
                          <label className="text-xs font-medium text-slate-600 whitespace-nowrap">Top-K</label>
                          <input
                            type="number" min={1} max={20} value={topK}
                            onChange={e => setTopK(Number(e.target.value))}
                            className="w-20 px-2.5 py-1.5 border border-slate-200 rounded-lg text-sm text-slate-900 focus:outline-none focus:ring-2 focus:ring-violet-500"
                          />
                        </div>
                        <div className="flex items-center gap-2">
                          <label className="text-xs font-medium text-slate-600 whitespace-nowrap">Threshold</label>
                          <input
                            type="number" min={0} max={1} step={0.05} value={threshold}
                            onChange={e => setThreshold(Number(e.target.value))}
                            className="w-24 px-2.5 py-1.5 border border-slate-200 rounded-lg text-sm text-slate-900 focus:outline-none focus:ring-2 focus:ring-violet-500"
                          />
                          <span className="text-xs text-slate-300">0.25 rec.</span>
                        </div>
                      </div>
                    )}
                  </div>
                </form>
              </div>
            </div>

            {/* Suggestions */}
            {history.length === 0 && (
              <div className="bg-white rounded-2xl border border-slate-200 shadow-sm overflow-hidden">
                <div className="px-5 py-3 border-b border-slate-100">
                  <p className="text-xs font-bold text-slate-500 uppercase tracking-widest flex items-center gap-2">
                    <Lightbulb className="w-3.5 h-3.5 text-amber-400" />
                    Try asking
                  </p>
                </div>
                <div className="p-3 space-y-1.5">
                  {SUGGESTIONS.map((s, i) => (
                    <button
                      key={i}
                      onClick={() => setQuestion(s)}
                      className="w-full text-left text-xs text-slate-600 hover:text-violet-700 hover:bg-violet-50 px-3 py-2.5 rounded-xl transition border border-transparent hover:border-violet-100 leading-snug"
                    >
                      {s}
                    </button>
                  ))}
                </div>
              </div>
            )}

            {/* History */}
            {history.length > 0 && (
              <div className="bg-white rounded-2xl border border-slate-200 shadow-sm overflow-hidden">
                <div className="px-5 py-3 border-b border-slate-100">
                  <p className="text-xs font-bold text-slate-500 uppercase tracking-widest flex items-center gap-2">
                    <Clock className="w-3.5 h-3.5 text-slate-400" />
                    History · {history.length}
                  </p>
                </div>
                <div className="p-2 space-y-1 max-h-72 overflow-y-auto">
                  {history.map(entry => (
                    <button
                      key={entry.id}
                      onClick={() => setCurrentId(entry.id)}
                      className={`w-full text-left rounded-xl px-3 py-2.5 text-xs transition border ${
                        entry.id === currentId
                          ? "border-violet-200 bg-violet-50"
                          : "border-transparent hover:bg-slate-50"
                      }`}
                    >
                      <span className={`line-clamp-2 font-medium leading-snug ${entry.id === currentId ? "text-violet-800" : "text-slate-700"}`}>
                        {entry.question}
                      </span>
                      <div className="flex items-center gap-2 mt-1.5">
                        {entry.chatResult.has_sufficient_evidence
                          ? <span className="text-[10px] bg-emerald-100 text-emerald-700 px-1.5 py-0.5 rounded-full font-semibold">
                              {entry.chatResult.chunks_used} chunk{entry.chatResult.chunks_used !== 1 ? "s" : ""}
                            </span>
                          : <span className="text-[10px] bg-amber-100 text-amber-700 px-1.5 py-0.5 rounded-full font-semibold">
                              no evidence
                            </span>}
                        <span className="text-[10px] text-slate-300 ml-auto">
                          {entry.ts.toLocaleTimeString([], { hour: "2-digit", minute: "2-digit" })}
                        </span>
                      </div>
                    </button>
                  ))}
                </div>
              </div>
            )}
          </div>

          {/* ── RIGHT: answer area (flex column, card scrolls internally) ── */}
          <div className="lg:col-span-2 lg:h-full lg:min-h-0 flex flex-col gap-4">

            {/* Loading skeleton */}
            {loading && (
              <div className="flex-1 min-h-0 flex flex-col bg-white rounded-2xl border border-slate-200 shadow-sm overflow-hidden">
                <div className="px-5 py-4 border-b border-slate-100 bg-gradient-to-r from-violet-50 to-indigo-50 flex items-center gap-3 shrink-0">
                  <div className="bg-gradient-to-br from-violet-600 to-indigo-600 p-2 rounded-lg animate-pulse">
                    <Bot className="w-4 h-4 text-white" />
                  </div>
                  <span className="text-sm font-bold text-violet-800">Thinking…</span>
                  <Loader2 className="w-4 h-4 text-violet-400 animate-spin ml-auto" />
                </div>
                <div className="flex-1 min-h-0 overflow-y-auto p-6 space-y-3">
                  {[90, 70, 85, 55].map((w, i) => (
                    <div key={i} className="h-3 rounded-full bg-slate-100 animate-pulse" style={{ width: `${w}%`, animationDelay: `${i * 0.12}s` }} />
                  ))}
                  <div className="h-24 rounded-xl bg-slate-100 animate-pulse mt-4" style={{ animationDelay: "0.5s" }} />
                </div>
              </div>
            )}

            {/* Answer */}
            {!loading && current && (
              <>
                {/* Evidence banner */}
                {current.chatResult.has_sufficient_evidence ? (
                  <div className="shrink-0 flex items-center gap-3 bg-emerald-50 border border-emerald-200 rounded-xl px-4 py-3">
                    <CheckCircle2 className="w-4 h-4 text-emerald-600 shrink-0" />
                    <span className="text-sm text-emerald-700 font-semibold">
                      Found {current.chatResult.chunks_used} relevant chunk{current.chatResult.chunks_used !== 1 ? "s" : ""}
                    </span>
                    {current.chatResult.best_score != null && (
                      <span className="text-sm text-emerald-600">
                        · best match {(current.chatResult.best_score * 100).toFixed(0)}%
                      </span>
                    )}
                    <span className="ml-auto text-xs text-emerald-400 font-mono">
                      threshold {(current.chatResult.threshold * 100).toFixed(0)}%
                    </span>
                  </div>
                ) : (
                  <div className="shrink-0 flex items-start gap-3 bg-amber-50 border border-amber-200 rounded-xl px-4 py-3">
                    <Info className="w-4 h-4 text-amber-600 shrink-0 mt-0.5" />
                    <div>
                      <p className="text-sm font-bold text-amber-800">Insufficient evidence</p>
                      <p className="text-xs text-amber-600 mt-0.5 leading-relaxed">
                        {current.chatResult.insufficient_evidence_reason ?? "No relevant code found above the similarity threshold."}
                      </p>
                    </div>
                  </div>
                )}

                {/* Question bubble */}
                <div className="shrink-0 flex items-start gap-3 justify-end">
                  <div className="bg-gradient-to-br from-violet-600 to-indigo-600 text-white px-4 py-3 rounded-2xl rounded-tr-sm max-w-[85%] shadow-sm shadow-violet-200">
                    <p className="text-sm leading-relaxed font-medium">{current.question}</p>
                  </div>
                  <div className="w-8 h-8 rounded-full bg-slate-200 flex items-center justify-center shrink-0">
                    <User className="w-4 h-4 text-slate-500" />
                  </div>
                </div>

                {/* AI answer card — fills remaining height, tab content scrolls */}
                {(current.chatResult.answer || evidenceCount > 0) && (
                  <div className="flex-1 min-h-0 flex flex-col bg-white rounded-2xl border border-slate-200 shadow-sm overflow-hidden">
                    {/* Tab bar (fixed) */}
                    <div className="shrink-0 flex items-center border-b border-slate-100 bg-gradient-to-r from-slate-50 to-white px-4">
                      <div className="flex items-center gap-1 py-1">
                        <button
                          onClick={() => setActiveTab("answer")}
                          className={`flex items-center gap-2 px-3.5 py-2 rounded-lg text-xs font-semibold transition ${
                            activeTab === "answer"
                              ? "bg-violet-100 text-violet-700"
                              : "text-slate-500 hover:text-slate-700 hover:bg-slate-100"
                          }`}
                        >
                          <Bot className="w-3.5 h-3.5" />
                          AI Answer
                        </button>
                        {evidenceCount > 0 && (
                          <button
                            onClick={() => setActiveTab("evidence")}
                            className={`flex items-center gap-2 px-3.5 py-2 rounded-lg text-xs font-semibold transition ${
                              activeTab === "evidence"
                                ? "bg-violet-100 text-violet-700"
                                : "text-slate-500 hover:text-slate-700 hover:bg-slate-100"
                            }`}
                          >
                            <Code2 className="w-3.5 h-3.5" />
                            Code Evidence
                            <span className="bg-slate-200 text-slate-600 px-1.5 py-0.5 rounded-full text-[10px] font-bold leading-none">
                              {evidenceCount}
                            </span>
                          </button>
                        )}
                      </div>
                      <span className="ml-auto text-xs text-slate-300 font-mono pr-1 truncate max-w-xs hidden sm:block">
                        {current.ts.toLocaleTimeString([], { hour: "2-digit", minute: "2-digit" })}
                      </span>
                    </div>

                    {/* Tab content — scrolls internally instead of the page */}
                    <div className="flex-1 min-h-0 overflow-y-auto">
                      {activeTab === "answer" && current.chatResult.answer && (
                        <div className="flex items-start gap-3 p-5">
                          <div className="bg-gradient-to-br from-violet-600 to-indigo-600 p-2 rounded-xl shrink-0 shadow-sm">
                            <Bot className="w-4 h-4 text-white" />
                          </div>
                          <div className="flex-1 min-w-0">
                            <AnswerText text={current.chatResult.answer} />
                          </div>
                        </div>
                      )}

                      {activeTab === "evidence" && current.retrievalResult && evidenceCount > 0 && (
                        <div className="p-5">
                          <EvidencePanel chunks={current.retrievalResult.chunks} />
                        </div>
                      )}
                    </div>
                  </div>
                )}

                {/* Empty state */}
                {!current.chatResult.answer && evidenceCount === 0 && (
                  <div className="flex-1 min-h-0 bg-white rounded-2xl border border-dashed border-slate-200 shadow-none text-center flex flex-col items-center justify-center py-16">
                    <Code2 className="w-10 h-10 mx-auto mb-3 text-slate-200" />
                    <p className="text-sm font-bold text-slate-500">No matching code chunks found</p>
                    <p className="text-xs text-slate-400 mt-1">
                      Try lowering the similarity threshold or rephrasing your question.
                    </p>
                  </div>
                )}
              </>
            )}

            {/* Welcome state */}
            {!loading && !current && (
              <div className="flex-1 min-h-0 bg-white rounded-2xl border border-dashed border-slate-200 shadow-none flex flex-col items-center justify-center px-8 text-center">
                <div className="bg-gradient-to-br from-violet-100 to-indigo-100 p-5 rounded-2xl mb-4">
                  <MessageSquare className="w-10 h-10 text-violet-400" />
                </div>
                <h2 className="text-base font-bold text-slate-700 mb-1">Ask your first question</h2>
                <p className="text-sm text-slate-400 max-w-sm leading-relaxed">
                  Type a question on the left and the AI will search the indexed codebase and explain what it finds.
                </p>
                <div className="mt-6 flex flex-wrap gap-2 justify-center">
                  {SUGGESTIONS.slice(0, 2).map((s, i) => (
                    <button
                      key={i}
                      onClick={() => setQuestion(s)}
                      className="text-xs text-violet-700 bg-violet-50 hover:bg-violet-100 border border-violet-100 px-3 py-1.5 rounded-full transition"
                    >
                      {s}
                    </button>
                  ))}
                </div>
              </div>
            )}
          </div>
        </div>
      </div>
    </div>
  );
}
