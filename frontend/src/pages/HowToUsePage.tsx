import React, { useState } from "react";
import { useNavigate } from "react-router-dom";
import {
  GitBranch,
  UserPlus,
  Link2,
  Zap,
  MessageSquare,
  CheckCircle2,
  ArrowRight,
  ChevronRight,
  Code2,
  Bot,
  Search,
  BookOpen,
} from "lucide-react";

// ---- Step data --------------------------------------------------------------

const STEPS = [
  {
    number: "01",
    icon: UserPlus,
    color: "#3b82f6",
    title: "Create an Account",
    subtitle: "Sign up in under 10 seconds",
    desc: "Register with your email and a password (min 8 characters). No credit card or OAuth needed -- just a local account.",
    tips: [
      "Use any email address",
      "Password must be at least 8 characters",
      "Your data is isolated -- nobody else can see your repos",
    ],
    preview: (
      <div className="rounded-xl overflow-hidden" style={{ background: "#0f172a", border: "1px solid rgba(59,130,246,0.2)" }}>
        <div className="flex gap-1.5 px-3 py-2.5 border-b border-slate-800">
          <span className="w-2.5 h-2.5 rounded-full bg-red-500/70" />
          <span className="w-2.5 h-2.5 rounded-full bg-yellow-500/70" />
          <span className="w-2.5 h-2.5 rounded-full bg-green-500/70" />
          <span className="ml-2 text-[11px] text-slate-500 font-mono">repopilot / auth</span>
        </div>
        <div className="p-4 space-y-3">
          <div className="flex border-b border-slate-800">
            <div className="flex-1 py-2 text-center text-xs text-slate-500">Sign In</div>
            <div className="flex-1 py-2 text-center text-xs text-blue-400 font-semibold border-b-2 border-blue-500">Register</div>
          </div>
          {[["Email", "you@example.com"], ["Password", "..."]].map(([label, ph]) => (
            <div key={label}>
              <p className="text-[10px] text-slate-500 uppercase tracking-wide mb-1">{label}</p>
              <div className="bg-slate-800 border border-slate-700 rounded-lg px-3 py-2 text-xs text-slate-500 font-mono">
                {ph}
              </div>
            </div>
          ))}
          <div className="bg-blue-600 rounded-lg py-2 text-center text-xs font-semibold text-white">
            Create Account
          </div>
        </div>
      </div>
    ),
  },
  {
    number: "02",
    icon: Link2,
    color: "#a78bfa",
    title: "Index a Repository",
    subtitle: "Paste any public GitHub URL",
    desc: "Go to the Dashboard, paste a GitHub URL, and hit Index. RepoPilot clones the repo, discovers all code files, splits them into chunks, and generates vector embeddings automatically.",
    tips: [
      "Only public GitHub repositories are supported",
      "Large repos (10 000+ files) may take 1-2 minutes",
      "Watch the live progress bar -- it polls every 2.5 seconds",
    ],
    preview: (
      <div className="rounded-xl overflow-hidden" style={{ background: "#0f172a", border: "1px solid rgba(167,139,250,0.2)" }}>
        <div className="flex gap-1.5 px-3 py-2.5 border-b border-slate-800">
          <span className="w-2.5 h-2.5 rounded-full bg-red-500/70" />
          <span className="w-2.5 h-2.5 rounded-full bg-yellow-500/70" />
          <span className="w-2.5 h-2.5 rounded-full bg-green-500/70" />
          <span className="ml-2 text-[11px] text-slate-500 font-mono">Dashboard</span>
        </div>
        <div className="p-4 space-y-3">
          <p className="text-[10px] text-slate-500 uppercase tracking-wide">GitHub Repository URL</p>
          <div className="flex gap-2">
            <div className="flex-1 bg-slate-800 border border-slate-700 rounded-lg px-3 py-2 text-[11px] text-slate-400 font-mono truncate">
              https://github.com/owner/repo
            </div>
            <div className="bg-violet-600 rounded-lg px-3 py-2 text-[11px] font-semibold text-white whitespace-nowrap">
              Index
            </div>
          </div>
          <div className="bg-slate-800/60 border border-slate-700/60 rounded-lg p-3">
            <div className="flex items-center justify-between mb-2">
              <span className="text-[11px] text-slate-300 font-semibold">Indexing Running</span>
              <span className="text-[10px] text-blue-400 bg-blue-500/10 px-2 py-0.5 rounded-full">Polling 2.5s</span>
            </div>
            <div className="h-1 bg-slate-700 rounded-full overflow-hidden">
              <div className="h-full bg-violet-500 w-3/5 rounded-full animate-pulse" />
            </div>
          </div>
        </div>
      </div>
    ),
  },
  {
    number: "03",
    icon: MessageSquare,
    color: "#34d399",
    title: "Ask a Question",
    subtitle: "Natural language -- no query syntax",
    desc: "Switch to the Q&A tab. Select your repository (or search all), type a plain-English question, and press Ask. The system embeds your query, searches the vector store, and sends matching chunks to the LLM.",
    tips: [
      'Be specific: "How is JWT token expiry set?" beats "auth?"',
      "Use Ctrl+Enter to submit from the textarea",
      "Lower the similarity threshold if you get no results",
    ],
    preview: (
      <div className="rounded-xl overflow-hidden" style={{ background: "#0f172a", border: "1px solid rgba(52,211,153,0.2)" }}>
        <div className="flex gap-1.5 px-3 py-2.5 border-b border-slate-800">
          <span className="w-2.5 h-2.5 rounded-full bg-red-500/70" />
          <span className="w-2.5 h-2.5 rounded-full bg-yellow-500/70" />
          <span className="w-2.5 h-2.5 rounded-full bg-green-500/70" />
          <span className="ml-2 text-[11px] text-slate-500 font-mono">Q&A</span>
        </div>
        <div className="p-4 space-y-3">
          <div className="bg-slate-800 border border-slate-700 rounded-lg px-3 py-2 text-[11px] text-slate-400">
            torvalds/linux (indexed)
          </div>
          <div className="bg-slate-800 border border-emerald-500/40 rounded-lg px-3 py-2 text-[11px] text-slate-300 font-mono leading-relaxed">
            How is memory allocation handled in the kernel slab allocator?
          </div>
          <div className="flex justify-end">
            <div className="flex items-center gap-1.5 bg-emerald-600 rounded-lg px-3 py-1.5 text-[11px] font-semibold text-white">
              <Search className="w-3 h-3" />
              Ask
            </div>
          </div>
        </div>
      </div>
    ),
  },
  {
    number: "04",
    icon: Bot,
    color: "#f59e0b",
    title: "Read the Answer",
    subtitle: "Grounded, cited, evidence-backed",
    desc: "You get three things: an AI-generated answer citing specific files and line numbers, an evidence panel showing the exact code chunks used, and similarity scores so you know how confident the retrieval was.",
    tips: [
      "Click any evidence chunk to expand the raw code",
      "Copy button on each chunk lets you grab the code instantly",
      "History is kept -- click a past question to revisit it",
    ],
    preview: (
      <div className="rounded-xl overflow-hidden" style={{ background: "#0f172a", border: "1px solid rgba(245,158,11,0.2)" }}>
        <div className="flex gap-1.5 px-3 py-2.5 border-b border-slate-800">
          <span className="w-2.5 h-2.5 rounded-full bg-red-500/70" />
          <span className="w-2.5 h-2.5 rounded-full bg-yellow-500/70" />
          <span className="w-2.5 h-2.5 rounded-full bg-green-500/70" />
          <span className="ml-2 text-[11px] text-slate-500 font-mono">AI Answer</span>
        </div>
        <div className="p-4 space-y-3">
          <div className="flex items-center gap-2 bg-emerald-500/10 border border-emerald-500/20 rounded-lg px-3 py-1.5">
            <CheckCircle2 className="w-3.5 h-3.5 text-emerald-400" />
            <span className="text-[11px] text-emerald-300">Found 3 chunks · best 94%</span>
          </div>
          <div className="bg-blue-500/5 border border-blue-500/15 rounded-lg p-3">
            <div className="flex items-center gap-1.5 mb-2">
              <Bot className="w-3.5 h-3.5 text-blue-400" />
              <span className="text-[10px] font-semibold text-blue-300">AI Answer</span>
            </div>
            <p className="text-[11px] text-slate-300 leading-relaxed">
              The slab allocator is defined in{" "}
              <code className="text-amber-300 bg-amber-900/30 px-1 rounded">mm/slab.c</code> at
              line 1,204. It uses a cache of fixed-size objects...
            </p>
          </div>
          <div className="flex items-center gap-2 bg-slate-800/50 rounded-lg px-3 py-2">
            <Code2 className="w-3.5 h-3.5 text-slate-400" />
            <span className="text-[11px] text-slate-400">mm/slab.c lines 1204-1231 · 94%</span>
          </div>
        </div>
      </div>
    ),
  },
];

// ---- FAQ data ----------------------------------------------------------------

const FAQS = [
  {
    q: "Does it work with private repositories?",
    a: "Currently only public GitHub repositories are supported. Private repo support via GitHub tokens is planned.",
  },
  {
    q: "What embedding model is used?",
    a: "all-MiniLM-L6-v2 running locally via sentence-transformers. No data is sent to any embedding API -- it runs fully on-device.",
  },
  {
    q: "Which LLM generates the answers?",
    a: "OpenRouter routes to particle-ai/particle-1:free by default. You can swap any OpenRouter-compatible model in the .env file.",
  },
  {
    q: "What if the AI says there is insufficient evidence?",
    a: "Lower the similarity threshold (try 0.15-0.20) or rephrase your question to use terms that appear literally in the code.",
  },
  {
    q: "Can I delete a repository?",
    a: "Yes -- hover a repository card on the Dashboard to reveal the delete button. This removes all chunks, embeddings, and the local clone.",
  },
];

function FAQItem({ q, a }: { q: string; a: string }) {
  const [open, setOpen] = useState(false);
  return (
    <div
      className="border rounded-xl overflow-hidden transition-colors"
      style={{
        borderColor: "rgba(255,255,255,0.08)",
        background: open ? "rgba(15,23,42,0.8)" : "rgba(15,23,42,0.4)",
      }}
    >
      <button
        onClick={() => setOpen((v) => !v)}
        className="w-full flex items-center justify-between px-5 py-4 text-left gap-4"
      >
        <span className="text-sm font-medium text-slate-200">{q}</span>
        <ChevronRight
          className={`w-4 h-4 text-slate-500 shrink-0 transition-transform ${open ? "rotate-90" : ""}`}
        />
      </button>
      {open && (
        <div className="px-5 pb-4 text-sm text-slate-400 leading-relaxed border-t border-white/5 pt-3">
          {a}
        </div>
      )}
    </div>
  );
}

// ---- Page -------------------------------------------------------------------

export default function HowToUsePage() {
  const navigate = useNavigate();

  return (
    <div className="min-h-screen bg-gray-950 text-slate-100 overflow-x-hidden">

      {/* Ambient blobs */}
      <div className="pointer-events-none fixed inset-0 overflow-hidden">
        <div
          className="absolute -top-40 right-0 w-[500px] h-[500px] rounded-full opacity-10"
          style={{ background: "radial-gradient(circle, #a78bfa 0%, transparent 70%)" }}
        />
        <div
          className="absolute bottom-0 -left-20 w-[400px] h-[400px] rounded-full opacity-10"
          style={{ background: "radial-gradient(circle, #3b82f6 0%, transparent 70%)" }}
        />
      </div>

      {/* Nav */}
      <nav className="relative z-10 flex items-center justify-between px-6 md:px-12 py-5">
        <button
          onClick={() => navigate("/landing")}
          className="flex items-center gap-2.5 hover:opacity-80 transition"
        >
          <div className="bg-blue-600 p-2 rounded-xl">
            <GitBranch className="w-4 h-4 text-white" />
          </div>
          <span className="font-bold text-white text-lg tracking-tight">RepoPilot AI</span>
        </button>
        <button
          onClick={() => navigate("/auth")}
          className="flex items-center gap-1.5 text-sm font-medium text-white bg-blue-600 hover:bg-blue-500 px-4 py-2 rounded-lg transition btn-glow"
        >
          Get Started
          <ArrowRight className="w-4 h-4" />
        </button>
      </nav>

      {/* Hero */}
      <section className="relative z-10 text-center px-6 pt-12 pb-16 max-w-3xl mx-auto">
        <div className="inline-flex items-center gap-2 bg-violet-500/10 border border-violet-500/25 rounded-full px-4 py-1.5 mb-6">
          <BookOpen className="w-3.5 h-3.5 text-violet-400" />
          <span className="text-xs text-violet-300 font-medium">Step-by-step guide</span>
        </div>
        <h1 className="text-4xl md:text-5xl font-extrabold text-white mb-5 leading-tight">
          How to use{" "}
          <span className="gradient-text">RepoPilot AI</span>
        </h1>
        <p className="text-slate-400 text-base leading-relaxed max-w-xl mx-auto">
          From zero to your first AI-powered code answer in four steps.
          No configuration required.
        </p>
      </section>

      {/* Steps */}
      <section className="relative z-10 max-w-5xl mx-auto px-6 pb-20">
        <div className="space-y-6">
          {STEPS.map((step, idx) => {
            const Icon = step.icon;
            return (
              <div key={step.number}>
                <div
                  className="glass rounded-2xl overflow-hidden fade-up"
                  style={{
                    animationDelay: `${idx * 0.12}s`,
                    border: `1px solid ${step.color}20`,
                  }}
                >
                  <div className="grid grid-cols-1 md:grid-cols-2 gap-0">
                    {/* Left -- info */}
                    <div className="p-7 md:p-8 flex flex-col justify-center">
                      <div className="flex items-center gap-3 mb-5">
                        <div
                          className="flex items-center justify-center w-10 h-10 rounded-xl shrink-0"
                          style={{
                            background: `${step.color}15`,
                            border: `1px solid ${step.color}30`,
                          }}
                        >
                          <Icon className="w-5 h-5" style={{ color: step.color }} />
                        </div>
                        <div>
                          <span
                            className="text-[11px] font-bold tracking-widest block"
                            style={{ color: step.color }}
                          >
                            STEP {step.number}
                          </span>
                          <h3 className="text-lg font-bold text-white leading-tight">
                            {step.title}
                          </h3>
                        </div>
                      </div>

                      <p className="text-xs font-semibold uppercase tracking-wide mb-2" style={{ color: step.color }}>
                        {step.subtitle}
                      </p>
                      <p className="text-sm text-slate-400 leading-relaxed mb-5">
                        {step.desc}
                      </p>

                      <ul className="space-y-2">
                        {step.tips.map((tip, ti) => (
                          <li key={ti} className="flex items-start gap-2 text-xs text-slate-400">
                            <CheckCircle2
                              className="w-3.5 h-3.5 mt-0.5 shrink-0"
                              style={{ color: step.color }}
                            />
                            {tip}
                          </li>
                        ))}
                      </ul>
                    </div>

                    {/* Right -- preview */}
                    <div
                      className="flex items-center justify-center p-7 md:p-8 border-t md:border-t-0 md:border-l"
                      style={{
                        borderColor: `${step.color}15`,
                        background: `${step.color}05`,
                      }}
                    >
                      <div className="w-full max-w-xs">{step.preview}</div>
                    </div>
                  </div>
                </div>

                {/* Connector arrow between steps */}
                {idx < STEPS.length - 1 && (
                  <div className="flex justify-center py-2">
                    <div
                      className="flex items-center justify-center w-7 h-7 rounded-full"
                      style={{ background: "rgba(255,255,255,0.04)", border: "1px solid rgba(255,255,255,0.08)" }}
                    >
                      <ChevronRight className="w-4 h-4 text-slate-600 rotate-90" />
                    </div>
                  </div>
                )}
              </div>
            );
          })}
        </div>
      </section>

      {/* FAQ */}
      <section className="relative z-10 max-w-2xl mx-auto px-6 pb-20">
        <div className="text-center mb-10">
          <h2 className="text-2xl font-bold text-white mb-2">Common questions</h2>
          <p className="text-slate-400 text-sm">Click any question to expand the answer.</p>
        </div>
        <div className="space-y-3">
          {FAQS.map((f) => (
            <FAQItem key={f.q} {...f} />
          ))}
        </div>
      </section>

      {/* CTA */}
      <section className="relative z-10 max-w-2xl mx-auto px-6 pb-20 text-center">
        <div
          className="glass rounded-3xl p-10"
          style={{ border: "1px solid rgba(99,102,241,0.2)" }}
        >
          <h2 className="text-2xl font-bold text-white mb-3">Ready to try it?</h2>
          <p className="text-slate-400 text-sm mb-7">
            Create your account and index your first repository in under two minutes.
          </p>
          <button
            onClick={() => navigate("/auth")}
            className="inline-flex items-center gap-2 px-8 py-3.5 bg-blue-600 hover:bg-blue-500 text-white font-semibold rounded-xl transition btn-glow text-sm"
          >
            Get Started Free
            <ArrowRight className="w-4 h-4" />
          </button>
        </div>
      </section>

      {/* Footer */}
      <footer className="relative z-10 border-t border-white/5 px-6 py-8 text-center">
        <div className="flex items-center justify-center gap-2 mb-2">
          <div className="bg-blue-600/80 p-1.5 rounded-lg">
            <GitBranch className="w-3.5 h-3.5 text-white" />
          </div>
          <span className="text-sm font-semibold text-slate-300">RepoPilot AI</span>
        </div>
        <p className="text-xs text-slate-600">
          FastAPI · pgvector · sentence-transformers · OpenRouter · React
        </p>
      </footer>
    </div>
  );
}
