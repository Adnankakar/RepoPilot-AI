import React, { useState } from "react";
import { Light as SyntaxHighlighter } from "react-syntax-highlighter";
import { atomOneDark } from "react-syntax-highlighter/dist/esm/styles/hljs";
// Register only the languages we actually need so the bundle stays small
import python     from "react-syntax-highlighter/dist/esm/languages/hljs/python";
import typescript from "react-syntax-highlighter/dist/esm/languages/hljs/typescript";
import javascript from "react-syntax-highlighter/dist/esm/languages/hljs/javascript";
import bash       from "react-syntax-highlighter/dist/esm/languages/hljs/bash";
import sql        from "react-syntax-highlighter/dist/esm/languages/hljs/sql";
import json       from "react-syntax-highlighter/dist/esm/languages/hljs/json";
import yaml       from "react-syntax-highlighter/dist/esm/languages/hljs/yaml";
import cpp        from "react-syntax-highlighter/dist/esm/languages/hljs/cpp";
import java       from "react-syntax-highlighter/dist/esm/languages/hljs/java";
import go         from "react-syntax-highlighter/dist/esm/languages/hljs/go";
import rust       from "react-syntax-highlighter/dist/esm/languages/hljs/rust";
import { RetrievedChunk } from "../api";
import { FileCode, ChevronDown, ChevronRight, Hash, Copy, Check } from "lucide-react";

SyntaxHighlighter.registerLanguage("python",     python);
SyntaxHighlighter.registerLanguage("typescript", typescript);
SyntaxHighlighter.registerLanguage("javascript", javascript);
SyntaxHighlighter.registerLanguage("bash",       bash);
SyntaxHighlighter.registerLanguage("sql",        sql);
SyntaxHighlighter.registerLanguage("json",       json);
SyntaxHighlighter.registerLanguage("yaml",       yaml);
SyntaxHighlighter.registerLanguage("cpp",        cpp);
SyntaxHighlighter.registerLanguage("java",       java);
SyntaxHighlighter.registerLanguage("go",         go);
SyntaxHighlighter.registerLanguage("rust",      rust);

// ── Language detection from file extension ───────────────────────────────────
function detectLang(filePath: string): string {
  const ext = filePath.split(".").pop()?.toLowerCase() ?? "";
  const map: Record<string, string> = {
    py: "python", pyw: "python",
    ts: "typescript", tsx: "typescript",
    js: "javascript", jsx: "javascript",
    sh: "bash", bash: "bash", zsh: "bash",
    sql: "sql",
    json: "json",
    yaml: "yaml", yml: "yaml",
    cpp: "cpp", cc: "cpp", cxx: "cpp", h: "cpp", hpp: "cpp",
    java: "java",
    go: "go",
    rs: "rust",
  };
  return map[ext] ?? "python"; // default to python for unknown
}

// ── Score tiers (semantic, data-encoded) ─────────────────────────────────────
function scoreBadge(s: number) {
  if (s >= 0.8) return { badge: "bg-emerald-50 text-emerald-700 border border-emerald-200", bar: "bg-emerald-500", dot: "bg-emerald-500" };
  if (s >= 0.6) return { badge: "bg-blue-50 text-blue-700 border border-blue-200",           bar: "bg-blue-500",   dot: "bg-blue-500"   };
  if (s >= 0.4) return { badge: "bg-amber-50 text-amber-700 border border-amber-200",        bar: "bg-amber-400",  dot: "bg-amber-400"  };
  return               { badge: "bg-slate-100 text-slate-600 border border-slate-200",       bar: "bg-slate-400",  dot: "bg-slate-400"  };
}

// ── Copy button ───────────────────────────────────────────────────────────────
function CopyBtn({ text }: { text: string }) {
  const [copied, setCopied] = useState(false);
  return (
    <button
      onClick={() => {
        navigator.clipboard.writeText(text).then(() => {
          setCopied(true);
          setTimeout(() => setCopied(false), 1800);
        });
      }}
      className="flex items-center gap-1.5 text-xs text-slate-400 hover:text-slate-200 transition-colors px-2.5 py-1 rounded-md hover:bg-white/10"
    >
      {copied ? (
        <>
          <Check className="w-3.5 h-3.5 text-emerald-400" />
          <span className="text-emerald-400">Copied</span>
        </>
      ) : (
        <>
          <Copy className="w-3.5 h-3.5" />
          <span>Copy</span>
        </>
      )}
    </button>
  );
}

// ── Main component ────────────────────────────────────────────────────────────
interface Props { chunks: RetrievedChunk[]; }

export default function EvidencePanel({ chunks }: Props) {
  const [openIdx, setOpenIdx] = useState<number | null>(0);
  if (!chunks.length) return null;

  return (
    <div className="space-y-3">
      {chunks.map((chunk, idx) => {
        const open  = openIdx === idx;
        const pct   = Math.round(chunk.similarity * 100);
        const { badge, bar, dot } = scoreBadge(chunk.similarity);
        const lang  = detectLang(chunk.file_path);
        const fileName = chunk.file_path.split("/").pop() ?? chunk.file_path;

        return (
          <div
            key={chunk.id}
            className="rounded-xl overflow-hidden border border-slate-200 bg-white"
          >
            {/* ── Accordion header ──────────────────────────────────────── */}
            <button
              onClick={() => setOpenIdx(open ? null : idx)}
              aria-expanded={open}
              className="w-full flex items-center gap-3 px-4 py-3 text-left hover:bg-slate-50 transition-colors"
            >
              {/* Score dot */}
              <span className={`w-2 h-2 rounded-full shrink-0 ${dot}`} />

              {/* File icon + path */}
              <FileCode className="w-4 h-4 text-slate-400 shrink-0" />
              <span className="flex-1 min-w-0">
                <span className="text-sm font-semibold text-slate-800 truncate block">{fileName}</span>
                <span className="text-xs text-slate-400 font-mono truncate block">
                  {chunk.file_path.length > fileName.length ? chunk.file_path : ""}
                </span>
              </span>

              {/* Line range */}
              <span className="hidden sm:flex items-center gap-1 text-xs text-slate-500 shrink-0 font-mono bg-slate-100 px-2 py-0.5 rounded-md">
                <Hash className="w-3 h-3" />{chunk.start_line}–{chunk.end_line}
              </span>

              {/* Similarity bar + badge */}
              <div className="hidden sm:flex items-center gap-1.5 shrink-0">
                <div className="w-16 h-1.5 rounded-full bg-slate-100 overflow-hidden">
                  <div className={`h-full rounded-full ${bar} transition-all`} style={{ width: `${pct}%` }} />
                </div>
                <span className={`text-xs font-semibold px-2 py-0.5 rounded-md whitespace-nowrap tabular-nums ${badge}`}>{pct}%</span>
              </div>

              {open
                ? <ChevronDown  className="w-4 h-4 text-slate-400 shrink-0" />
                : <ChevronRight className="w-4 h-4 text-slate-400 shrink-0" />}
            </button>

            {/* ── Code body ─────────────────────────────────────────────── */}
            {open && (
              <div className="border-t border-slate-200">
                {/* Code toolbar — dark strip */}
                <div
                  className="flex items-center justify-between px-4 py-2 code-toolbar"
                >
                  <div className="flex items-center gap-3">
                    {/* macOS dots */}
                    <span className="flex gap-1.5">
                      <span className="w-3 h-3 rounded-full bg-red-500/80"   />
                      <span className="w-3 h-3 rounded-full bg-yellow-500/80"/>
                      <span className="w-3 h-3 rounded-full bg-green-500/80" />
                    </span>
                    <span className="text-xs font-mono text-slate-400">{chunk.file_path}</span>
                    <span
                      className="text-xs font-mono px-2 py-0.5 rounded"
                      style={{ background: "rgba(255,255,255,0.08)", color: "#94a3b8" }}
                    >
                      {lang}
                    </span>
                  </div>
                  <div className="flex items-center gap-2">
                    <span className="text-xs text-slate-500 font-mono tabular-nums">
                      lines {chunk.start_line}–{chunk.end_line}
                      {chunk.commit_sha && ` · ${chunk.commit_sha.slice(0, 7)}`}
                    </span>
                    <CopyBtn text={chunk.content} />
                  </div>
                </div>

                {/* Syntax-highlighted code */}
                <div className="overflow-x-auto code-surface">
                  <SyntaxHighlighter
                    language={lang}
                    style={atomOneDark}
                    showLineNumbers
                    startingLineNumber={chunk.start_line}
                    lineNumberStyle={{
                      minWidth: "3em",
                      paddingRight: "1em",
                      color: "#4a5568",
                      userSelect: "none",
                      fontSize: "0.75rem",
                    }}
                    customStyle={{
                      margin: 0,
                      padding: "1rem 1.25rem",
                      background: "#1a1f2e",
                      fontSize: "0.8rem",
                      lineHeight: "1.65",
                      borderRadius: 0,
                    }}
                    codeTagProps={{ style: { fontFamily: "'Fira Code','Cascadia Code',Consolas,monospace" } }}
                  >
                    {chunk.content}
                  </SyntaxHighlighter>
                </div>
              </div>
            )}
          </div>
        );
      })}
    </div>
  );
}
