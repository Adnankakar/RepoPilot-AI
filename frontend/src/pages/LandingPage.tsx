import React from "react";
import { useNavigate } from "react-router-dom";
import {
  GitBranch,
  Search,
  MessageSquare,
  Zap,
  Shield,
  Layers,
  ArrowRight,
  BookOpen,
  ChevronRight,
  Bot,
  FileCode,
  Activity,
  CheckCircle2,
  Hash,
} from "lucide-react";

// ─── Feature cards ────────────────────────────────────────────────────────────
const FEATURES = [
  {
    icon: Search,
    title: "Semantic search",
    desc: "Dense vector embeddings via all-MiniLM-L6-v2 find the exact lines of code relevant to your question.",
  },
  {
    icon: MessageSquare,
    title: "Grounded answers",
    desc: "An OpenRouter LLM reads only the retrieved evidence and writes answers that cite specific files and lines.",
  },
  {
    icon: Zap,
    title: "One-click indexing",
    desc: "Paste a GitHub URL. RepoPilot clones, parses, chunks, embeds, and stores — ready in seconds.",
  },
  {
    icon: Shield,
    title: "Secure by design",
    desc: "JWT auth, per-user repository isolation, and similarity thresholds that prevent hallucinated answers.",
  },
  {
    icon: Layers,
    title: "Full-stack and open",
    desc: "FastAPI backend · pgvector · React frontend. Swap the LLM or embedding model from a single .env file.",
  },
  {
    icon: GitBranch,
    title: "Multi-repo Q&A",
    desc: "Ask questions across all your indexed repositories at once, or scope the search to a single repo.",
  },
];

// ─── Output preview cards (the "from raw code to clear answers" section) ──────
function OutputAnswerPreview() {
  return (
    <div className="space-y-3">
      <div className="flex items-center gap-2 text-xs">
        <Bot className="w-4 h-4 text-blue-600 shrink-0" />
        <span className="font-medium text-slate-700">AI answer</span>
      </div>
      <p className="text-sm text-slate-600 leading-relaxed">
        JWT authentication lives in{" "}
        <code className="text-slate-800 bg-slate-100 px-1.5 py-0.5 rounded text-xs font-mono">app/core/security.py</code>.
        The <code className="text-slate-800 bg-slate-100 px-1.5 py-0.5 rounded text-xs font-mono">create_access_token()</code>{" "}
        function encodes a payload with a 30-minute expiry using HS256.
      </p>
      <div className="rounded-lg overflow-hidden border border-slate-200">
        <div className="flex items-center justify-between px-3 py-2 code-toolbar">
          <span className="text-xs font-mono text-slate-400">core/security.py</span>
          <span className="text-xs font-mono px-1.5 py-0.5 rounded text-slate-400" style={{ background: "rgba(255,255,255,0.08)" }}>python</span>
        </div>
        <pre className="p-3 text-xs leading-relaxed font-mono text-slate-300 overflow-x-auto code-surface">
<span className="text-blue-400">def</span> <span className="text-yellow-300">create_access_token</span>(data):
  payload = data.copy()
  payload[<span className="text-emerald-300">"exp"</span>] = now() + <span className="text-violet-300">timedelta</span>(minutes=30)
  <span className="text-blue-400">return</span> jwt.encode(payload, SECRET)
        </pre>
      </div>
    </div>
  );
}

function OutputEvidencePreview() {
  const rows = [
    { file: "core/security.py", lines: "12–28", score: 94, bar: "bg-emerald-500", badge: "text-emerald-700 bg-emerald-50 border-emerald-200" },
    { file: "api/auth.py",       lines: "45–61", score: 87, bar: "bg-blue-500",   badge: "text-blue-700 bg-blue-50 border-blue-200"   },
    { file: "api/deps.py",       lines: "8–19",  score: 71, bar: "bg-amber-400",  badge: "text-amber-700 bg-amber-50 border-amber-200" },
  ];
  return (
    <div className="space-y-2">
      <div className="flex items-center gap-2 text-xs">
        <FileCode className="w-4 h-4 text-blue-600 shrink-0" />
        <span className="font-medium text-slate-700">Code evidence</span>
      </div>
      {rows.map((c) => (
        <div key={c.file} className="flex items-center gap-2 bg-white border border-slate-200 rounded-lg px-3 py-2">
          <div className="flex-1 min-w-0">
            <p className="text-xs font-mono text-slate-700 truncate">{c.file}</p>
            <p className="text-xs text-slate-400">lines {c.lines}</p>
          </div>
          <div className="flex items-center gap-1.5 shrink-0">
            <div className="w-12 h-1 bg-slate-100 rounded-full overflow-hidden">
              <div className={`h-full ${c.bar} rounded-full`} style={{ width: `${c.score}%` }} />
            </div>
            <span className={`text-xs font-semibold tabular-nums px-1.5 py-0.5 rounded border ${c.badge}`}>{c.score}%</span>
          </div>
        </div>
      ))}
    </div>
  );
}

function OutputIndexingPreview() {
  return (
    <div className="space-y-3">
      <div className="flex items-center gap-2 text-xs">
        <Activity className="w-4 h-4 text-blue-600 shrink-0" />
        <span className="font-medium text-slate-700">Indexing status</span>
      </div>
      <div className="flex items-center justify-between">
        <span className="text-xs font-mono text-slate-500">torvalds/linux</span>
        <span className="text-xs font-medium bg-emerald-50 text-emerald-700 border border-emerald-200 px-2 py-0.5 rounded-md">
          Indexed
        </span>
      </div>
      <div className="h-1 bg-slate-100 rounded-full overflow-hidden">
        <div className="h-full bg-emerald-500 rounded-full w-full" />
      </div>
      <div className="grid grid-cols-3 gap-2">
        {[["Files", "1,284"], ["Chunks", "8,931"], ["Vectors", "8,931"]].map(([k, v]) => (
          <div key={k} className="bg-white border border-slate-200 rounded-lg px-2 py-1.5 text-center">
            <p className="text-xs text-slate-400">{k}</p>
            <p className="text-sm font-semibold text-slate-700 tabular-nums">{v}</p>
          </div>
        ))}
      </div>
    </div>
  );
}

const OUTPUT_PREVIEWS = [
  { label: "AI answer",        render: <OutputAnswerPreview /> },
  { label: "Code evidence",    render: <OutputEvidencePreview /> },
  { label: "Indexing status",  render: <OutputIndexingPreview /> },
];

// ─── Hero product preview (a real Q&A mockup built from components) ──────────
function HeroPreview() {
  return (
    <div className="bg-white rounded-xl border border-slate-200 overflow-hidden shadow-sm">
      {/* window chrome */}
      <div className="flex items-center gap-2 px-4 py-3 border-b border-slate-100 bg-slate-50">
        <span className="flex gap-1.5">
          <span className="w-2.5 h-2.5 rounded-full bg-slate-300" />
          <span className="w-2.5 h-2.5 rounded-full bg-slate-300" />
          <span className="w-2.5 h-2.5 rounded-full bg-slate-300" />
        </span>
        <span className="text-xs font-mono text-slate-400 ml-1">RepoPilot · Q&amp;A</span>
      </div>

      <div className="p-5 space-y-4">
        {/* question */}
        <div className="flex items-start gap-3 justify-end">
          <div className="bg-blue-600 text-white px-3.5 py-2.5 rounded-xl rounded-tr-sm max-w-[85%]">
            <p className="text-sm leading-relaxed">How is JWT authentication implemented?</p>
          </div>
          <div className="w-8 h-8 rounded-full bg-slate-200 flex items-center justify-center shrink-0">
            <span className="text-xs font-semibold text-slate-600">U</span>
          </div>
        </div>

        {/* evidence banner */}
        <div className="flex items-center gap-2 bg-emerald-50 border border-emerald-200 rounded-lg px-3 py-2">
          <CheckCircle2 className="w-4 h-4 text-emerald-600 shrink-0" />
          <span className="text-xs text-emerald-700 font-medium">Found 3 relevant chunks · best match 94%</span>
        </div>

        {/* answer */}
        <div className="flex items-start gap-3">
          <div className="bg-blue-50 p-2 rounded-lg shrink-0">
            <Bot className="w-4 h-4 text-blue-600" />
          </div>
          <div className="flex-1 min-w-0">
            <p className="text-sm text-slate-600 leading-relaxed">
              Authentication is handled in{" "}
              <code className="text-slate-800 bg-slate-100 px-1.5 py-0.5 rounded text-xs font-mono">app/core/security.py</code>.
              <code className="text-slate-800 bg-slate-100 px-1.5 py-0.5 rounded text-xs font-mono">create_access_token()</code>{" "}
              encodes a payload with a 30-minute expiry using HS256.
            </p>
          </div>
        </div>

        {/* evidence chunk row */}
        <div className="flex items-center gap-3 bg-white border border-slate-200 rounded-lg px-3 py-2.5">
          <span className="w-2 h-2 rounded-full bg-emerald-500 shrink-0" />
          <FileCode className="w-4 h-4 text-slate-400 shrink-0" />
          <span className="flex-1 min-w-0">
            <span className="text-sm font-semibold text-slate-800 truncate block">security.py</span>
            <span className="text-xs text-slate-400 font-mono truncate block">app/core/security.py</span>
          </span>
          <span className="hidden sm:flex items-center gap-1 text-xs text-slate-500 font-mono">
            <Hash className="w-3 h-3" />12–28
          </span>
          <span className="text-xs font-semibold tabular-nums px-2 py-0.5 rounded-md bg-emerald-50 text-emerald-700 border border-emerald-200">94%</span>
        </div>
      </div>
    </div>
  );
}

// ─── Page ─────────────────────────────────────────────────────────────────────
export default function LandingPage() {
  const navigate = useNavigate();

  return (
    <div className="min-h-screen bg-slate-50 text-slate-900">

      {/* ── Nav ────────────────────────────────────────────────────────────── */}
      <nav className="flex items-center justify-between px-6 md:px-10 h-16 border-b border-slate-200 bg-white">
        <div className="flex items-center gap-2.5">
          <div className="bg-blue-600 p-2 rounded-lg">
            <GitBranch className="w-4 h-4 text-white" />
          </div>
          <span className="font-semibold text-slate-900 text-lg tracking-tight">RepoPilot AI</span>
        </div>
        <div className="flex items-center gap-2">
          <button
            onClick={() => navigate("/how-to-use")}
            className="hidden sm:flex items-center gap-1.5 text-sm text-slate-600 hover:text-slate-900 transition px-3 py-2 rounded-lg hover:bg-slate-100"
          >
            <BookOpen className="w-4 h-4" />
            How to use
          </button>
          <button
            onClick={() => navigate("/auth")}
            className="text-sm font-semibold text-white bg-blue-600 hover:bg-blue-700 px-4 py-2 rounded-lg transition"
          >
            Get started
          </button>
        </div>
      </nav>

      {/* ── Hero (asymmetric, product-led) ─────────────────────────────────── */}
      <section className="max-w-6xl mx-auto px-6 md:px-10 py-16 lg:py-20">
        <div className="grid grid-cols-1 lg:grid-cols-2 gap-12 lg:gap-16 items-center">
          {/* Left — message */}
          <div>
            <p className="text-sm text-slate-500 mb-5">Semantic search over your own repositories</p>
            <h1 className="text-4xl md:text-5xl font-semibold text-slate-900 leading-tight tracking-tight mb-6">
              Understand any codebase in seconds
            </h1>
            <p className="text-base text-slate-600 leading-relaxed max-w-xl mb-8">
              Index a GitHub repository, ask questions in plain English, and get
              answers grounded in the exact lines of code — with similarity
              scores and source citations.
            </p>
            <div className="flex flex-col sm:flex-row items-start sm:items-center gap-3">
              <button
                onClick={() => navigate("/auth")}
                className="flex items-center gap-2 px-6 py-3 bg-blue-600 hover:bg-blue-700 text-white font-semibold rounded-lg transition text-sm"
              >
                Get started
                <ArrowRight className="w-4 h-4" />
              </button>
              <button
                onClick={() => navigate("/how-to-use")}
                className="flex items-center gap-2 px-6 py-3 bg-white border border-slate-200 hover:bg-slate-100 text-slate-700 font-medium rounded-lg transition text-sm"
              >
                <BookOpen className="w-4 h-4" />
                How it works
              </button>
            </div>
          </div>

          {/* Right — real product preview */}
          <div className="lg:pl-4">
            <HeroPreview />
          </div>
        </div>
      </section>

      {/* ── From raw code to clear answers ──────────────────────────────────── */}
      <section className="max-w-6xl mx-auto px-6 md:px-10 py-16 border-t border-slate-200">
        <div className="mb-10 max-w-2xl">
          <h2 className="text-2xl md:text-3xl font-semibold text-slate-900 mb-3 tracking-tight">
            From raw code to clear answers
          </h2>
          <p className="text-slate-600 text-sm leading-relaxed">
            Ask a question and get a grounded AI answer, the evidence chunks it
            used, and the similarity scores — all in one view.
          </p>
        </div>

        <div className="grid grid-cols-1 md:grid-cols-3 gap-5">
          {OUTPUT_PREVIEWS.map((p) => (
            <div key={p.label} className="bg-white border border-slate-200 rounded-xl p-5">
              {p.render}
            </div>
          ))}
        </div>
      </section>

      {/* ── Features grid ──────────────────────────────────────────────────── */}
      <section className="max-w-6xl mx-auto px-6 md:px-10 py-16 border-t border-slate-200">
        <div className="mb-10 max-w-2xl">
          <h2 className="text-2xl md:text-3xl font-semibold text-slate-900 mb-3 tracking-tight">
            Everything you need
          </h2>
          <p className="text-slate-600 text-sm leading-relaxed">
            A complete RAG pipeline — from GitHub clone to grounded LLM answer.
          </p>
        </div>

        <div className="grid grid-cols-1 sm:grid-cols-2 lg:grid-cols-3 gap-4">
          {FEATURES.map(({ icon: Icon, title, desc }) => (
            <div
              key={title}
              className="bg-white border border-slate-200 rounded-xl p-5"
            >
              <div className="inline-flex p-2.5 rounded-lg bg-slate-100 mb-4">
                <Icon className="w-5 h-5 text-slate-500" />
              </div>
              <h3 className="text-sm font-semibold text-slate-900 mb-1.5">{title}</h3>
              <p className="text-sm text-slate-500 leading-relaxed">{desc}</p>
            </div>
          ))}
        </div>
      </section>

      {/* ── CTA ────────────────────────────────────────────────────────────── */}
      <section className="max-w-6xl mx-auto px-6 md:px-10 py-16 border-t border-slate-200">
        <div className="bg-white border border-slate-200 rounded-2xl p-10 md:p-14 text-center">
          <h2 className="text-2xl md:text-3xl font-semibold text-slate-900 mb-3 tracking-tight">
            Ready to explore your codebase?
          </h2>
          <p className="text-slate-600 text-sm mb-8 max-w-md mx-auto leading-relaxed">
            Create a free account, paste a GitHub URL, and ask your first
            question in under two minutes.
          </p>
          <button
            onClick={() => navigate("/auth")}
            className="inline-flex items-center gap-2 px-8 py-3.5 bg-blue-600 hover:bg-blue-700 text-white font-semibold rounded-lg transition text-sm"
          >
            Get started
            <ChevronRight className="w-4 h-4" />
          </button>
        </div>
      </section>

      {/* ── Footer ─────────────────────────────────────────────────────────── */}
      <footer className="border-t border-slate-200 px-6 md:px-10 py-8">
        <div className="max-w-6xl mx-auto flex flex-col sm:flex-row items-center justify-between gap-3">
          <div className="flex items-center gap-2">
            <div className="bg-blue-600 p-1.5 rounded-md">
              <GitBranch className="w-3.5 h-3.5 text-white" />
            </div>
            <span className="text-sm font-semibold text-slate-700">RepoPilot AI</span>
          </div>
          <p className="text-xs text-slate-400">
            FastAPI · pgvector · sentence-transformers · OpenRouter · React
          </p>
        </div>
      </footer>
    </div>
  );
}
