import React, { useState } from "react";
import { RetrievedChunk } from "../api";
import { FileCode, ChevronDown, ChevronRight, Hash } from "lucide-react";

interface Props {
  chunks: RetrievedChunk[];
}

export default function EvidencePanel({ chunks }: Props) {
  const [openIdx, setOpenIdx] = useState<number | null>(0);

  if (chunks.length === 0) return null;

  return (
    <div className="space-y-2">
      <h3 className="text-sm font-semibold text-gray-600 uppercase tracking-wide mb-3">
        Evidence ({chunks.length} chunk{chunks.length !== 1 ? "s" : ""})
      </h3>
      {chunks.map((chunk, idx) => {
        const open = openIdx === idx;
        const scorePercent = Math.round(chunk.similarity * 100);
        return (
          <div
            key={chunk.id}
            className="border border-gray-200 rounded-xl overflow-hidden bg-white shadow-sm"
          >
            {/* Header */}
            <button
              onClick={() => setOpenIdx(open ? null : idx)}
              className="flex items-center justify-between w-full px-4 py-3 text-left hover:bg-gray-50 transition"
            >
              <div className="flex items-center gap-3 min-w-0">
                <FileCode className="w-4 h-4 text-blue-500 shrink-0" />
                <span className="text-sm font-mono text-gray-800 truncate">
                  {chunk.file_path}
                </span>
                <span className="flex items-center gap-0.5 text-xs text-gray-400 shrink-0">
                  <Hash className="w-3 h-3" />
                  {chunk.start_line}–{chunk.end_line}
                </span>
              </div>
              <div className="flex items-center gap-3 shrink-0 ml-2">
                <span
                  className={`text-xs font-semibold px-2 py-0.5 rounded-full ${
                    scorePercent >= 80
                      ? "bg-green-100 text-green-700"
                      : scorePercent >= 60
                      ? "bg-blue-100 text-blue-700"
                      : "bg-gray-100 text-gray-600"
                  }`}
                >
                  {scorePercent}% match
                </span>
                {open ? (
                  <ChevronDown className="w-4 h-4 text-gray-400" />
                ) : (
                  <ChevronRight className="w-4 h-4 text-gray-400" />
                )}
              </div>
            </button>

            {/* Code snippet */}
            {open && (
              <div className="border-t border-gray-100">
                {/* Citation bar */}
                <div className="flex items-center justify-between px-4 py-2 bg-gray-50 border-b border-gray-100">
                  <span className="text-xs text-gray-500 font-mono">
                    Lines {chunk.start_line}–{chunk.end_line}
                    {chunk.commit_sha && (
                      <span className="ml-3 text-gray-400">
                        @ {chunk.commit_sha.slice(0, 7)}
                      </span>
                    )}
                  </span>
                  <span className="text-xs text-gray-400">
                    similarity {chunk.similarity.toFixed(4)}
                  </span>
                </div>
                {/* Code */}
                <pre className="px-4 py-3 text-xs text-gray-800 font-mono overflow-x-auto whitespace-pre bg-gray-900 text-gray-100 leading-relaxed">
                  {chunk.content}
                </pre>
              </div>
            )}
          </div>
        );
      })}
    </div>
  );
}
