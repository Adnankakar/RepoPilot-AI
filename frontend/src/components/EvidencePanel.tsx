import React, { useState } from "react";
import { RetrievedChunk } from "../api";
import { FileCode, ChevronDown, ChevronRight, Hash, Copy, Check } from "lucide-react";

interface Props {
  chunks: RetrievedChunk[];
}

/** Tailwind colour pair based on similarity score. */
function scoreStyle(score: number): { badge: string; bar: string } {
  if (score >= 0.8) return { badge: "bg-emerald-100 text-emerald-700 border border-emerald-200", bar: "bg-emerald-500" };
  if (score >= 0.6) return { badge: "bg-blue-100 text-blue-700 border border-blue-200", bar: "bg-blue-500" };
  if (score >= 0.4) return { badge: "bg-amber-100 text-amber-700 border border-amber-200", bar: "bg-amber-500" };
  return { badge: "bg-gray-100 text-gray-600 border border-gray-200", bar: "bg-gray-400" };
}

function CopyButton({ text }: { text: string }) {
  const [copied, setCopied] = useState(false);
  const copy = () => {
    navigator.clipboard.writeText(text).then(() => {
      setCopied(true);
      setTimeout(() => setCopied(false), 1500);
    });
  };
  return (
    <button
      onClick={copy}
      title="Copy code"
      className="flex items-center gap-1 text-xs text-gray-400 hover:text-gray-700 transition px-2 py-1 rounded hover:bg-gray-200"
    >
      {copied ? <Check className="w-3.5 h-3.5 text-emerald-500" /> : <Copy className="w-3.5 h-3.5" />}
      {copied ? "Copied" : "Copy"}
    </button>
  );
}

export default function EvidencePanel({ chunks }: Props) {
  const [openIdx, setOpenIdx] = useState<number | null>(0);

  if (chunks.length === 0) return null;

  return (
    <div className="space-y-3">
      <h3 className="text-xs font-semibold text-gray-500 uppercase tracking-widest mb-3">
        Source Evidence — {chunks.length} chunk{chunks.length !== 1 ? "s" : ""}
      </h3>

      {chunks.map((chunk, idx) => {
        const open = openIdx === idx;
        const scorePercent = Math.round(chunk.similarity * 100);
        const { badge, bar } = scoreStyle(chunk.similarity);

        return (
          <div
            key={chunk.id}
            className="border border-gray-200 rounded-xl overflow-hidden bg-white shadow-sm"
          >
            {/* ── Header ───────────────────────────────────────────────── */}
            <button
              onClick={() => setOpenIdx(open ? null : idx)}
              className="flex items-center justify-between w-full px-4 py-3 text-left hover:bg-gray-50 transition-colors"
            >
              <div className="flex items-center gap-2 min-w-0">
                <FileCode className="w-4 h-4 text-blue-500 shrink-0" />
                <span className="text-sm font-mono text-gray-800 truncate">
                  {chunk.file_path}
                </span>
                <span className="flex items-center gap-0.5 text-xs text-gray-400 shrink-0">
                  <Hash className="w-3 h-3" />
                  {chunk.start_line}–{chunk.end_line}
                </span>
              </div>

              <div className="flex items-center gap-2 shrink-0 ml-2">
                <div className="hidden sm:flex items-center gap-1.5">
                  <div className="w-16 h-1.5 rounded-full bg-gray-100 overflow-hidden">
                    <div
                      className={`h-full rounded-full ${bar}`}
                      style={{ width: `${scorePercent}%` }}
                    />
                  </div>
                </div>
                <span className={`text-xs font-semibold px-2 py-0.5 rounded-full ${badge}`}>
                  {scorePercent}% match
                </span>
                {open
                  ? <ChevronDown className="w-4 h-4 text-gray-400" />
                  : <ChevronRight className="w-4 h-4 text-gray-400" />}
              </div>
            </button>

            {/* ── Code body ─────────────────────────────────────────────── */}
            {open && (
              <div className="border-t border-gray-200">
                {/* Meta bar */}
                <div className="flex items-center justify-between px-4 py-2 bg-gray-50 border-b border-gray-200">
                  <span className="text-xs text-gray-500 font-mono">
                    Lines {chunk.start_line}–{chunk.end_line}
                    {chunk.commit_sha && (
                      <span className="ml-3 text-gray-400">
                        @ {chunk.commit_sha.slice(0, 7)}
                      </span>
                    )}
                    <span className="ml-3 text-gray-400">
                      similarity {chunk.similarity.toFixed(4)}
                    </span>
                  </span>
                  <CopyButton text={chunk.content} />
                </div>

                {/*
                  Code block: white background, dark text, left accent border.
                  Explicit colour values avoid any OS-level dark-mode inversion.
                */}
                <div className="overflow-x-auto">
                  <pre
                    style={{
                      margin: 0,
                      padding: "1rem 1.25rem",
                      backgroundColor: "#ffffff",
                      color: "#1e293b",           /* slate-800 — readable on white */
                      borderLeft: "4px solid #3b82f6", /* blue-500 accent */
                      fontFamily: "'Fira Code', 'Cascadia Code', 'Consolas', 'Menlo', monospace",
                      fontSize: "0.8125rem",      /* 13 px */
                      lineHeight: "1.6",
                      whiteSpace: "pre",
                      overflowX: "auto",
                      tabSize: 2,
                    }}
                  >
                    {chunk.content}
                  </pre>
                </div>
              </div>
            )}
          </div>
        );
      })}
    </div>
  );
}
