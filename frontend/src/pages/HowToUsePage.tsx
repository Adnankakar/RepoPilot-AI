import React, { useState } from "react";
import { useNavigate } from "react-router-dom";
import {
  GitBranch,
  UserPlus,
  Link2,
  MessageSquare,
  Bot,
  ArrowRight,
  ChevronRight,
  CheckCircle2,
  Search,
  BookOpen,
  Hash,
} from "lucide-react";

// ---- Step data --------------------------------------------------------------

const STEPS = [
  {
    number: "01",
    icon: UserPlus,
    title: "Create an account",
    subtitle: "Sign up in under 10 seconds",
    desc: "Register with your email and a password (min 8 characters). No credit card or OAuth needed — just a local account.",
    tips: [
      "Use any email address",
      "Password must be at least 8 characters",
      "Your data is isolated — nobody else can see your repos",
    ],
    preview: (
      <div className="rounded-xl overflow-hidden border border-slate-200 bg-white">
        <div className="flex gap-1.5 px-3 py-2.5 border-b border-slate-100 bg-slate-50">
          <span className="w-2.5 h-2.5 rounded-full bg-slate-300" />
          <span className="w-2.5 h-2.5 rounded-full bg-slate-300" />
          <span className="w-2.5 h-2.5 rounded-full bg-slate-300" />
          <span className="ml-2 text-xs text-slate-400 font-mono">repopilot / auth</span>
        </div>
        <div className="p-4 space-y-3">
          <div className="flex border-b border-slate-100">
            <div className="flex-1 py-2 text-center text-xs text-slate-400">Sign in</div>
            <div className="flex-1 py-2 text-center text-xs text-blue-700 font-medium border-b-2 border-blue-600">Register</div>
          </div>
          {[["Email", "you@example.com"], ["Password", "••••••••"]].map(([label, ph]) => (
            <div key={label}>
              <p className="text-xs text-slate-500 mb-1">{label}</p>
              <div className="bg-slate-50 border border-slate-200 rounded-lg px-3 py-2 text-xs text-slate-400 font-mono">
                {ph}
              </div>
            </div>
          ))}
          <div className="bg-blue-600 rounded-lg py-2 text-center text-xs font-semibold text-white">
            Create account
          </div>
        </div>
      </div>
    ),
  },
  {
    number: "02",
    icon: Link2,
    title: "Index a repository",
    subtitle: "Paste any public GitHub URL",
    desc: "Go to the Dashboard, paste a GitHub URL, and hit Index. RepoPilot clones the repo, discovers all code files, splits them into chunks, and generates vector embeddings automatically.",
    tips: [
      "Only public GitHub repositories are supported",
      "Large repos (10 000+ files) may take 1–2 minutes",
      "Watch the live progress — it polls every 2.5 seconds",
    ],
    preview: (
      <div className="rounded-xl overflow-hidden border border-slate-200 bg-white">
        <div className="flex gap-1.5 px-3 py-2.5 border-b border-slate-100 bg-slate-50">
          <span className="w-2.5 h-2.5 rounded-full bg-slate-300" />
          <span className="w-2.5 h-2.5 rounded-full bg-slate-300" />
          <span className="w-2.5 h-2.5 rounded-full bg-slate-300" />
          <span className="ml-2 text-xs text-slate-400 font-mono">Dashboard</span>
        </div>
        <div className="p-4 space-y-3">
          <p className="text-xs text-slate-500">GitHub repository URL</p>
          <div className="flex gap-2">
            <div className="flex-1 bg-slate-50 border border-slate-200 rounded-lg px-3 py-2 text-xs text-slate-500 font-mono truncate">
              https://github.com/owner/repo
            </div>
            <div className="bg-blue-600 rounded-lg px-3 py-2 text-xs font-semibold text-white whitespace-nowrap">
              Index
            </div>
          </div>
          <div className="bg-slate-50 border border-slate-200 rounded-lg p-3">
            <div className="flex items-center justify-between mb-2">
              <span className="text-xs text-slate-700 font-medium">Indexing running</span>
              <span className="text-xs text-blue-700 bg-blue-50 border border-blue-100 px-2 py-0.5 rounded-md">Polling 2.5s</span>
            </div>
            <div className="h-1 bg-slate-100 rounded-full overflow-hidden">
              <div className="h-full w-1/3 bg-blue-500 rounded-full indeterminate" />
            </div>
          </div>
        </div>
      </div>
    ),
  },
  {
    number: "03",
    icon: MessageSquare,
    title: "Ask a question",
    subtitle: "Natural language — no query syntax",
    desc: "Switch to the Q&A tab. Select your repository (or search all), type a plain-English question, and press Ask. The system embeds your query, searches the vector store, and sends matching chunks to the LLM.",
    tips: [
      "Be specific: “How is JWT token expiry set?” beats “auth?”",
      "Use Ctrl+Enter to submit from the textarea",
      "Lower the similarity threshold if you get no results",
    ],
    preview: (
      <div className="rounded-xl overflow-hidden border border-slate-200 bg-white">
        <div className="flex gap-1.5 px-3 py-2.5 border-b border-slate-100 bg-slate-50">
          <span className="w-2.5 h-2.5 rounded-full bg-slate-300" />
          <span className="w-2.5 h-2.5 rounded-full bg-slate-300" />
          <span className="w-2.5 h-2.5 rounded-full bg-slate-300" />
          <span className="ml-2 text-xs text-slate-400 font-mono">Q&amp;A</span>
        </div>
        <div className="p-4 space-y-3">
          <div className="bg-slate-50 border border-slate-200 rounded-lg px-3 py-2 text-xs text-slate-500">
            torvalds/linux (indexed)
          </div>
          <div className="bg-slate-50 border border-slate-200 rounded-lg px-3 py-2 text-xs text-slate-700 font-mono leading-relaxed">
            How is memory allocation handled in the slab allocator?
          </div>
          <div className="flex justify-end">
            <div className="flex items-center gap-1.5 bg-blue-600 rounded-lg px-3 py-1.5 text-xs font-semibold text-white">
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
    title: "Read the answer",
    subtitle: "Grounded, cited, evidence-backed",
    desc: "You get three things: an AI-generated answer citing specific files and line numbers, an evidence panel showing the exact code chunks used, and similarity scores so you know how confident the retrieval was.",
    tips: [
      "Click any evidence chunk to expand the raw code",
      "Copy button on each chunk lets you grab the code instantly",
      "History is kept — click a past question to revisit it",
    ],
    preview: (
      <div className="rounded-xl overflow-hidden border border-slate-200 bg-white">
        <div className="flex gap-1.5 px-3 py-2.5 border-b border-slate-100 bg-slate-50">
          <span className="w-2.5 h-2.5 rounded-full bg-slate-300" />
          <span className="w-2.5 h-2.5 rounded-full bg-slate-300" />
          <span className="w-2.5 h-2.5 rounded-full bg-slate-300" />
          <span className="ml-2 text-xs text-slate-400 font-mono">AI answer</span>
        </div>
        <div className="p-4 space-y-3">
          <div className="flex items-center gap-2 bg-emerald-50 border border-emerald-200 rounded-lg px-3 py-1.5">
            <CheckCircle2 className="w-3.5 h-3.5 text-emerald-600" />
            <span className="text-xs text-emerald-700">Found 3 chunks · best 94%</span>
          </div>
          <div className="flex items-start gap-2">
            <div className="bg-blue-50 p-1.5 rounded-md shrink-0">
              <Bot className="w-3.5 h-3.5 text-blue-600" />
            </div>
            <p className="text-xs text-slate-600 leading-relaxed">
              The slab allocator is defined in{" "}
              <code className="text-slate-800 bg-slate-100 px-1 rounded text-xs font-mono">mm/slab.c</code> at
              line 1,204. It uses a cache of fixed-size objects…
            </p>
          </div>
          <div className="flex items-center gap-2 bg-slate-50 border border-slate-200 rounded-lg px-3 py-2">
            <span className="w-2 h-2 rounded-full bg-emerald-500 shrink-0" />
            <span className="text-xs font-mono text-slate-700">mm/slab.c</span>
            <span className="text-xs text-slate-400 font-mono flex items-center gap-0.5">
              <Hash className="w-3 h-3" />1204–1231
            </span>
            <span className="ml-auto text-xs font-semibold tabular-nums bg-emerald-50 text-emerald-700 border border-emerald-200 px-1.5 py-0.5 rounded-md">94%</span>
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
    a: "all-MiniLM-L6-v2 running locally via sentence-transformers. No data is sent to any embedding API — it runs fully on-device.",
  },
  {
    q: "Which LLM generates the answers?",
    a: "OpenRouter routes to particle-ai/particle-1:free by default. You can swap any OpenRouter-compatible model in the .env file.",
  },
  {
    q: "What if the AI says there is insufficient evidence?",
    a: "Lower the similarity threshold (try 0.15–0.20) or rephrase your question to use terms that appear literally in the code.",
  },
  {
    q: "Can I delete a repository?",
    a: "Yes — hover a repository card on the Dashboard to reveal the delete button. This removes all chunks, embeddings, and the local clone.",
  },
];

function FAQItem({ q, a }: { q: string; a: string }) {
  const [open, setOpen] = useState(false);
  return (
    <div className="border border-slate-200 rounded-lg overflow-hidden bg-white">
      <button
        onClick={() => setOpen((v) => !v)}
        aria-expanded={open}
        className="w-full flex items-center justify-between px-5 py-4 text-left gap-4 hover:bg-slate-50 transition-colors"
      >
        <span className="text-sm font-medium text-slate-800">{q}</span>
        <ChevronRight
          className={`w-4 h-4 text-slate-400 shrink-0 transition-transform ${open ? "rotate-90" : ""}`}
        />
      </button>
      {open && (
        <div className="px-5 pb-4 text-sm text-slate-500 leading-relaxed border-t border-slate-100 pt-3">
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
    <div className="min-h-screen bg-slate-50 text-slate-900">

      {/* Nav */}
      <nav className="flex items-center justify-between px-6 md:px-10 h-16 border-b border-slate-200 bg-white">
        <button
          onClick={() => navigate("/landing")}
          className="flex items-center gap-2.5 hover:opacity-80 transition"
        >
          <div className="bg-blue-600 p-2 rounded-lg">
            <GitBranch className="w-4 h-4 text-white" />
          </div>
          <span className="font-semibold text-slate-900 text-lg tracking-tight">RepoPilot AI</span>
        </button>
        <button
          onClick={() => navigate("/auth")}
          className="flex items-center gap-1.5 text-sm font-semibold text-white bg-blue-600 hover:bg-blue-700 px-4 py-2 rounded-lg transition"
        >
          Get started
          <ArrowRight className="w-4 h-4" />
        </button>
      </nav>

      {/* Hero */}
      <section className="text-center px-6 pt-14 pb-12 max-w-2xl mx-auto">
        <div className="inline-flex items-center gap-2 bg-blue-50 border border-blue-100 rounded-md px-3 py-1.5 mb-6">
          <BookOpen className="w-3.5 h-3.5 text-blue-600" />
          <span className="text-xs text-blue-700 font-medium">Step-by-step guide</span>
        </div>
        <h1 className="text-3xl md:text-4xl font-semibold text-slate-900 mb-4 leading-tight tracking-tight">
          How to use RepoPilot AI
        </h1>
        <p className="text-slate-600 text-base leading-relaxed max-w-xl mx-auto">
          From zero to your first AI-powered code answer in four steps.
          No configuration required.
        </p>
      </section>

      {/* Steps */}
      <section className="max-w-5xl mx-auto px-6 pb-20">
        <div className="space-y-6">
          {STEPS.map((step, idx) => {
            const Icon = step.icon;
            return (
              <div key={step.number}>
                <div className="bg-white border border-slate-200 rounded-xl overflow-hidden">
                  <div className="grid grid-cols-1 md:grid-cols-2 gap-0">
                    {/* Left — info */}
                    <div className="p-7 md:p-8 flex flex-col justify-center">
                      <div className="flex items-center gap-3 mb-5">
                        <div className="flex items-center justify-center w-10 h-10 rounded-lg shrink-0 bg-blue-50 ring-1 ring-blue-100">
                          <Icon className="w-5 h-5 text-blue-600" />
                        </div>
                        <div>
                          <span className="text-xs font-medium text-blue-600 block">
                            Step {step.number}
                          </span>
                          <h3 className="text-lg font-semibold text-slate-900 leading-tight">
                            {step.title}
                          </h3>
                        </div>
                      </div>

                      <p className="text-xs font-medium text-slate-500 mb-2">
                        {step.subtitle}
                      </p>
                      <p className="text-sm text-slate-600 leading-relaxed mb-5">
                        {step.desc}
                      </p>

                      <ul className="space-y-2">
                        {step.tips.map((tip, ti) => (
                          <li key={ti} className="flex items-start gap-2 text-sm text-slate-600">
                            <CheckCircle2
                              className="w-4 h-4 mt-0.5 shrink-0 text-blue-600"
                            />
                            {tip}
                          </li>
                        ))}
                      </ul>
                    </div>

                    {/* Right — preview */}
                    <div className="flex items-center justify-center p-7 md:p-8 border-t md:border-t-0 md:border-l border-slate-100 bg-slate-50">
                      <div className="w-full max-w-xs">{step.preview}</div>
                    </div>
                  </div>
                </div>

                {/* Connector between steps */}
                {idx < STEPS.length - 1 && (
                  <div className="flex justify-center py-2">
                    <div className="flex items-center justify-center w-7 h-7 rounded-full border border-slate-200 bg-white">
                      <ChevronRight className="w-4 h-4 text-slate-400 rotate-90" />
                    </div>
                  </div>
                )}
              </div>
            );
          })}
        </div>
      </section>

      {/* FAQ */}
      <section className="max-w-2xl mx-auto px-6 pb-20">
        <div className="text-center mb-10">
          <h2 className="text-2xl font-semibold text-slate-900 mb-2 tracking-tight">Common questions</h2>
          <p className="text-slate-500 text-sm">Click any question to expand the answer.</p>
        </div>
        <div className="space-y-3">
          {FAQS.map((f) => (
            <FAQItem key={f.q} {...f} />
          ))}
        </div>
      </section>

      {/* CTA */}
      <section className="max-w-2xl mx-auto px-6 pb-20 text-center">
        <div className="bg-white border border-slate-200 rounded-2xl p-10">
          <h2 className="text-2xl font-semibold text-slate-900 mb-3 tracking-tight">Ready to try it?</h2>
          <p className="text-slate-600 text-sm mb-7">
            Create your account and index your first repository in under two minutes.
          </p>
          <button
            onClick={() => navigate("/auth")}
            className="inline-flex items-center gap-2 px-8 py-3.5 bg-blue-600 hover:bg-blue-700 text-white font-semibold rounded-lg transition text-sm"
          >
            Get started
            <ArrowRight className="w-4 h-4" />
          </button>
        </div>
      </section>

      {/* Footer */}
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
