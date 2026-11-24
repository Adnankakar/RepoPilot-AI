import React, { useEffect, useRef } from "react";
import { useNavigate } from "react-router-dom";
import {
  GitBranch,
  Zap,
  Search,
  MessageSquare,
  ArrowRight,
  BookOpen,
  Shield,
  Layers,
  ChevronRight,
} from "lucide-react";

// ─── Code snippets that scroll through the marquee ───────────────────────────

const CODE_CARDS_ROW1 = [
  {
    file: "auth.py",
    lang: "python",
    color: "#3b82f6",
    code: `def create_access_token(data: dict):
    payload = data.copy()
    payload["exp"] = datetime.utcnow()
               + timedelta(minutes=30)
    return jwt.encode(payload, SECRET_KEY)`,
  },
  {
    file: "retrieval_service.py",
    lang: "python",
    color: "#a78bfa",
    code: `def retrieve_relevant_chunks(
    db, question, user, top_k=5
):
    vec = provider.embed(question)
    return vector_search(db, vec, top_k)`,
  },
  {
    file: "embedding_provider.py",
    lang: "python",
    color: "#34d399",
    code: `class LocalEmbeddingProvider:
    def embed_batch(self, texts):
        model = self._get_model()
        return model.encode(texts,
            normalize_embeddings=True)`,
  },
  {
    file: "chat.py",
    lang: "python",
    color: "#f59e0b",
    code: `@router.post("/ask")
def ask_question(payload, db, user):
    retrieval = retrieve_chunks(...)
    prompt = build_prompt(question,
                          retrieval.chunks)
    return llm.call(prompt)`,
  },
  {
    file: "indexing_worker.py",
    lang: "python",
    color: "#ec4899",
    code: `def run_indexing_job(job_id: str):
    clone_repository(url, branch)
    files = discover_files(clone_path)
    chunks = chunk_all_files(files)
    embed_and_store(chunks)`,
  },
  {
    file: "code_chunk.py",
    lang: "python",
    color: "#06b6d4",
    code: `class CodeChunk(Base):
    __tablename__ = "code_chunks"
    embedding = mapped_column(
        Vector(384), nullable=True
    )  # pgvector cosine search`,
  },
];

const CODE_CARDS_ROW2 = [
  {
    file: "api.ts",
    lang: "typescript",
    color: "#60a5fa",
    code: `export async function askQuestion(
  question: string,
  repositoryId?: string,
): Promise<ChatAskResponse> {
  return request("/api/chat/ask", {
    method: "POST", body: ...
  });
}`,
  },
  {
    file: "EvidencePanel.tsx",
    lang: "tsx",
    color: "#c084fc",
    code: `export default function EvidencePanel(
  { chunks }: Props
) {
  return chunks.map(chunk => (
    <CodeBlock key={chunk.id}
      file={chunk.file_path} />
  ));
}`,
  },
  {
    file: "rag_orchestration.py",
    lang: "python",
    color: "#4ade80",
    code: `def build_prompt(question, evidence):
    snippets = format_evidence(evidence)
    return SYSTEM_PROMPT
        + snippets
        + f"\\nQuestion: {question}"`,
  },
  {
    file: "config.py",
    lang: "python",
    color: "#fb923c",
    code: `class Settings(BaseSettings):
    embedding_provider: str = "local"
    embedding_model: str = "all-MiniLM-L6-v2"
    llm_provider: str = "openrouter"
    retrieval_top_k: int = 5`,
  },
  {
    file: "QAPage.tsx",
    lang: "tsx",
    color: "#38bdf8",
    code: `const [chatResult, retrievalResult] =
  await Promise.allSettled([
    askQuestion(q, repoId, topK),
    queryRetrieval(q, repoId, topK),
  ]);`,
  },
];

// ─── Feature cards data ───────────────────────────────────────────────────────

const FEATURES = [
  {
    icon: Search,
    color: "text-blue-400",
    bg: "bg-blue-500/10 border-blue-500/20",
    title: "Semantic Search",
    desc: "Dense vector embeddings via all-MiniLM-L6-v2 find the exact lines of code relevant to your question.",
  },
  {
    icon: MessageSquare,
    color: "text-violet-400",
    bg: "bg-violet-500/10 border-violet-500/20",
    title: "LLM-Grounded Answers",
    desc: "OpenRouter LLM reads only the retrieved evidence and generates precise, citation-backed answers.",
  },
  {
    icon: Zap,
    color: "text-emerald-400",
    bg: "bg-emerald-500/10 border-emerald-500/20",
    title: "One-Click Indexing",
    desc: "Paste a GitHub URL. RepoPilot clones, parses, chunks, embeds, and stores — ready in seconds.",
  },
  {
    icon: Shield,
    color: "text-amber-400",
    bg: "bg-amber-500/10 border-amber-500/20",
    title: "Secure by Design",
    desc: "JWT auth, per-user repository isolation, and similarity thresholds that prevent hallucinated answers.",
  },
  {
    icon: Layers,
    color: "text-pink-400",
    bg: "bg-pink-500/10 border-pink-500/20",
    title: "Full-Stack Open",
    desc: "FastAPI backend · pgvector · React frontend. Swap the LLM or embedding model from a single .env file.",
  },
  {
    icon: GitBranch,
    color: "text-cyan-400",
    bg: "bg-cyan-500/10 border-cyan-500/20",
    title: "Multi-Repo Q&A",
    desc: "Ask questions across all your indexed repositories at once, or scope to a single repo.",
  },
];

// ─── Output preview cards (the "into this" section) ──────────────────────────

const OUTPUT_PREVIEWS = [
  {
    label: "AI Answer",
    color: "#3b82f6",
    icon: "🤖",
    content: (
      <div className="space-y-2 text-left">
        <p className="text-xs text-slate-300 leading-relaxed">
          JWT authentication is implemented in{" "}
          <code className="text-blue-300 bg-blue-900/40 px-1 rounded text-[11px]">app/core/security.py</code>.
          The <code className="text-blue-300 bg-blue-900/40 px-1 rounded text-[11px]">create_access_token()</code> function
          encodes a payload with a 30-minute expiry using the{" "}
          <code className="text-blue-300 bg-blue-900/40 px-1 rounded text-[11px]">HS256</code> algorithm.
        </p>
        <div
          className="rounded-lg p-2.5 text-[11px] font-mono text-emerald-300 leading-relaxed overflow-x-auto"
          style={{ background: "rgba(16,24,39,0.8)", borderLeft: "2px solid #3b82f6" }}
        >
          <span className="text-blue-400">def</span>{" "}
          <span className="text-yellow-300">create_access_token</span>
          <span className="text-white">(data):</span>
          <br />
          {"  "}<span className="text-slate-400"># expires in 30 min</span>
          <br />
          {"  "}<span className="text-blue-400">return</span> jwt.encode(payload, SECRET)
        </div>
      </div>
    ),
  },
  {
    label: "Code Evidence",
    color: "#a78bfa",
    icon: "📎",
    content: (
      <div className="space-y-1.5 text-left">
        {[
          { file: "core/security.py", lines: "12–28", score: 94, bar: "bg-emerald-400" },
          { file: "api/auth.py",       lines: "45–61", score: 87, bar: "bg-blue-400"   },
          { file: "api/deps.py",       lines: "8–19",  score: 71, bar: "bg-violet-400" },
        ].map((c) => (
          <div key={c.file} className="flex items-center gap-2 bg-slate-800/60 rounded-lg px-2.5 py-2">
            <div className="flex-1 min-w-0">
              <p className="text-[11px] font-mono text-slate-200 truncate">{c.file}</p>
              <p className="text-[10px] text-slate-500">lines {c.lines}</p>
            </div>
            <div className="flex items-center gap-1.5 shrink-0">
              <div className="w-12 h-1 bg-slate-700 rounded-full overflow-hidden">
                <div className={`h-full ${c.bar} rounded-full`} style={{ width: `${c.score}%` }} />
              </div>
              <span className="text-[10px] text-slate-400">{c.score}%</span>
            </div>
          </div>
        ))}
      </div>
    ),
  },
  {
    label: "Indexing Status",
    color: "#34d399",
    icon: "⚡",
    content: (
      <div className="space-y-2 text-left">
        <div className="flex items-center justify-between mb-1">
          <span className="text-xs text-slate-400">torvalds/linux</span>
          <span className="text-[11px] bg-emerald-500/20 text-emerald-400 px-2 py-0.5 rounded-full border border-emerald-500/30">
            Indexed
          </span>
        </div>
        <div className="h-1 bg-slate-700 rounded-full overflow-hidden">
          <div className="h-full bg-emerald-400 rounded-full w-full" />
        </div>
        <div className="grid grid-cols-3 gap-1.5 mt-1">
          {[["Files", "1,284"], ["Chunks", "8,931"], ["Vectors", "8,931"]].map(([k, v]) => (
            <div key={k} className="bg-slate-800/60 rounded-lg px-2 py-1.5 text-center">
              <p className="text-[10px] text-slate-500">{k}</p>
              <p className="text-xs font-semibold text-slate-200">{v}</p>
            </div>
          ))}
        </div>
      </div>
    ),
  },
];

// ─── Marquee row component ────────────────────────────────────────────────────

function CodeCard({ file, lang, color, code }: (typeof CODE_CARDS_ROW1)[0]) {
  return (
    <div
      className="shrink-0 w-64 rounded-xl overflow-hidden mx-2.5"
      style={{
        background: "rgba(15,23,42,0.85)",
        border: `1px solid ${color}30`,
        boxShadow: `0 0 20px ${color}15`,
      }}
    >
      {/* title bar */}
      <div
        className="flex items-center gap-2 px-3 py-2 border-b"
        style={{ borderColor: `${color}25`, background: `${color}10` }}
      >
        <span className="w-2.5 h-2.5 rounded-full bg-red-500/70" />
        <span className="w-2.5 h-2.5 rounded-full bg-yellow-500/70" />
        <span className="w-2.5 h-2.5 rounded-full bg-green-500/70" />
        <span className="ml-1 text-[11px] font-mono" style={{ color }}>
          {file}
        </span>
        <span className="ml-auto text-[10px] text-slate-600">{lang}</span>
      </div>
      {/* code */}
      <pre
        className="p-3 text-[11px] leading-relaxed font-mono text-slate-300 overflow-hidden whitespace-pre"
        style={{ maxHeight: 112 }}
      >
        {code}
      </pre>
    </div>
  );
}

function MarqueeRow({
  cards,
  direction,
}: {
  cards: typeof CODE_CARDS_ROW1;
  direction: "left" | "right";
}) {
  // Duplicate for seamless loop
  const doubled = [...cards, ...cards];
  return (
    <div className="overflow-hidden w-full">
      <div className={`flex ${direction === "left" ? "marquee-left" : "marquee-right"}`}>
        {doubled.map((c, i) => (
          <CodeCard key={i} {...c} />
        ))}
      </div>
    </div>
  );
}

// ─── Output preview card (animated) ──────────────────────────────────────────

function OutputCard({
  label,
  color,
  icon,
  content,
  delay,
}: (typeof OUTPUT_PREVIEWS)[0] & { delay: string }) {
  return (
    <div
      className="glass rounded-2xl overflow-hidden fade-up"
      style={{ animationDelay: delay, border: `1px solid ${color}25` }}
    >
      <div
        className="flex items-center gap-2 px-4 py-3 border-b"
        style={{ borderColor: `${color}20`, background: `${color}0d` }}
      >
        <span className="text-base">{icon}</span>
        <span className="text-sm font-semibold text-slate-200">{label}</span>
        <span
          className="ml-auto w-2 h-2 rounded-full animate-pulse"
          style={{ background: color }}
        />
      </div>
      <div className="p-4">{content}</div>
    </div>
  );
}

// ─── Page ─────────────────────────────────────────────────────────────────────

export default function LandingPage() {
  const navigate = useNavigate();

  return (
    <div className="min-h-screen bg-gray-950 text-slate-100 overflow-x-hidden">

      {/* ── Ambient blobs ──────────────────────────────────────────────────── */}
      <div className="pointer-events-none fixed inset-0 overflow-hidden">
        <div
          className="absolute -top-40 -left-40 w-[600px] h-[600px] rounded-full opacity-20"
          style={{ background: "radial-gradient(circle, #3b82f6 0%, transparent 70%)" }}
        />
        <div
          className="absolute top-1/3 -right-40 w-[500px] h-[500px] rounded-full opacity-15"
          style={{ background: "radial-gradient(circle, #a78bfa 0%, transparent 70%)" }}
        />
        <div
          className="absolute -bottom-20 left-1/3 w-[400px] h-[400px] rounded-full opacity-10"
          style={{ background: "radial-gradient(circle, #34d399 0%, transparent 70%)" }}
        />
      </div>

      {/* ── Nav ────────────────────────────────────────────────────────────── */}
      <nav className="relative z-10 flex items-center justify-between px-6 md:px-12 py-5">
        <div className="flex items-center gap-2.5">
          <div className="bg-blue-600 p-2 rounded-xl">
            <GitBranch className="w-4 h-4 text-white" />
          </div>
          <span className="font-bold text-white text-lg tracking-tight">RepoPilot AI</span>
        </div>
        <div className="flex items-center gap-3">
          <button
            onClick={() => navigate("/how-to-use")}
            className="hidden sm:flex items-center gap-1.5 text-sm text-slate-400 hover:text-white transition px-3 py-2 rounded-lg hover:bg-white/5"
          >
            <BookOpen className="w-4 h-4" />
            How to Use
          </button>
          <button
            onClick={() => navigate("/auth")}
            className="text-sm font-medium text-white bg-blue-600 hover:bg-blue-500 px-4 py-2 rounded-lg transition btn-glow"
          >
            Get Started
          </button>
        </div>
      </nav>

      {/* ── Hero ───────────────────────────────────────────────────────────── */}
      <section className="relative z-10 text-center px-6 pt-16 pb-10 max-w-4xl mx-auto">
        <div className="inline-flex items-center gap-2 bg-blue-500/10 border border-blue-500/25 rounded-full px-4 py-1.5 mb-8 fade-up">
          <span className="w-2 h-2 rounded-full bg-blue-400 animate-pulse" />
          <span className="text-xs text-blue-300 font-medium">
            Powered by all-MiniLM-L6-v2 + OpenRouter
          </span>
        </div>

        <h1 className="text-5xl md:text-6xl font-extrabold leading-tight mb-6 fade-up fade-up-1">
          Understand any{" "}
          <span className="gradient-text">codebase</span>
          <br />
          in seconds
        </h1>

        <p className="text-lg text-slate-400 max-w-2xl mx-auto mb-10 leading-relaxed fade-up fade-up-2">
          Index a GitHub repository, ask questions in plain English, and get
          AI-generated answers grounded in the exact lines of code — with
          similarity scores and source citations.
        </p>

        <div className="flex flex-col sm:flex-row items-center justify-center gap-4 fade-up fade-up-3">
          <button
            onClick={() => navigate("/auth")}
            className="flex items-center gap-2 px-8 py-3.5 bg-blue-600 hover:bg-blue-500 text-white font-semibold rounded-xl transition btn-glow text-sm"
          >
            Get Started Free
            <ArrowRight className="w-4 h-4" />
          </button>
          <button
            onClick={() => navigate("/how-to-use")}
            className="flex items-center gap-2 px-8 py-3.5 glass hover:bg-white/10 text-slate-200 font-medium rounded-xl transition text-sm border border-white/10"
          >
            <BookOpen className="w-4 h-4" />
            How it Works
          </button>
        </div>
      </section>

      {/* ── Code marquee strips ────────────────────────────────────────────── */}
      <section className="relative z-10 py-8 space-y-3 overflow-hidden">
        {/* Fade masks on the sides */}
        <div className="pointer-events-none absolute inset-y-0 left-0 w-32 z-10"
          style={{ background: "linear-gradient(to right, #030712, transparent)" }} />
        <div className="pointer-events-none absolute inset-y-0 right-0 w-32 z-10"
          style={{ background: "linear-gradient(to left, #030712, transparent)" }} />

        <MarqueeRow cards={CODE_CARDS_ROW1} direction="left" />
        <MarqueeRow cards={CODE_CARDS_ROW2} direction="right" />
      </section>

      {/* ── "Into this" output section ─────────────────────────────────────── */}
      <section className="relative z-10 max-w-5xl mx-auto px-6 py-16">
        <div className="text-center mb-12">
          <p className="text-xs font-semibold uppercase tracking-widest text-blue-400 mb-3">
            Into this
          </p>
          <h2 className="text-3xl md:text-4xl font-bold text-white mb-4">
            From raw code to clear answers
          </h2>
          <p className="text-slate-400 max-w-xl mx-auto text-sm leading-relaxed">
            Ask a question, get a grounded AI answer, the evidence chunks it
            used, and the similarity scores — all in one view.
          </p>
        </div>

        <div className="grid grid-cols-1 md:grid-cols-3 gap-5">
          {OUTPUT_PREVIEWS.map((p, i) => (
            <OutputCard
              key={p.label}
              {...p}
              delay={`${i * 0.15}s`}
            />
          ))}
        </div>
      </section>

      {/* ── Features grid ──────────────────────────────────────────────────── */}
      <section className="relative z-10 max-w-5xl mx-auto px-6 py-12">
        <div className="text-center mb-12">
          <h2 className="text-3xl font-bold text-white mb-3">Everything you need</h2>
          <p className="text-slate-400 text-sm max-w-lg mx-auto">
            A complete RAG pipeline — from GitHub clone to streaming LLM answer.
          </p>
        </div>

        <div className="grid grid-cols-1 sm:grid-cols-2 lg:grid-cols-3 gap-4">
          {FEATURES.map(({ icon: Icon, color, bg, title, desc }) => (
            <div
              key={title}
              className={`glass rounded-2xl p-5 border hover:scale-[1.02] transition-transform cursor-default ${bg}`}
            >
              <div className={`inline-flex p-2.5 rounded-xl ${bg} border mb-4`}>
                <Icon className={`w-5 h-5 ${color}`} />
              </div>
              <h3 className="text-sm font-semibold text-white mb-1.5">{title}</h3>
              <p className="text-xs text-slate-400 leading-relaxed">{desc}</p>
            </div>
          ))}
        </div>
      </section>

      {/* ── CTA bottom ─────────────────────────────────────────────────────── */}
      <section className="relative z-10 max-w-3xl mx-auto px-6 py-20 text-center">
        <div
          className="glass rounded-3xl p-10 md:p-14"
          style={{ border: "1px solid rgba(99,102,241,0.2)" }}
        >
          <h2 className="text-3xl md:text-4xl font-extrabold text-white mb-4">
            Ready to explore your codebase?
          </h2>
          <p className="text-slate-400 text-sm mb-8 max-w-md mx-auto leading-relaxed">
            Create a free account, paste a GitHub URL, and ask your first
            question in under two minutes.
          </p>
          <button
            onClick={() => navigate("/auth")}
            className="inline-flex items-center gap-2 px-10 py-4 bg-blue-600 hover:bg-blue-500 text-white font-semibold rounded-xl transition btn-glow text-sm"
          >
            Get Started
            <ChevronRight className="w-4 h-4" />
          </button>
        </div>
      </section>

      {/* ── Footer ─────────────────────────────────────────────────────────── */}
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
