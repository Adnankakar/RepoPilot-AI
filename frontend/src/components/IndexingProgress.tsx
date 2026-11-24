import React, { useEffect, useRef, useState } from "react";
import {
  getRepositoryStatus,
  getRepositorySkips,
  RepositoryStatusResponse,
  RepositoryFileSkipResponse,
} from "../api";
import { useError } from "../context/ErrorContext";
import {
  Loader2, CheckCircle2, XCircle, Clock,
  AlertTriangle, ChevronDown, ChevronRight,
} from "lucide-react";

const POLL_MS  = 2500;
const TERMINAL = new Set(["completed", "failed", "error"]);

function JobIcon({ s }: { s: string }) {
  if (s === "completed") return <CheckCircle2 className="w-5 h-5 text-emerald-500" />;
  if (s === "failed" || s === "error") return <XCircle className="w-5 h-5 text-red-500" />;
  if (s === "running") return <Loader2 className="w-5 h-5 text-blue-500 animate-spin" />;
  return <Clock className="w-5 h-5 text-slate-400" />;
}

function statusColor(s: string) {
  if (s === "completed") return "text-emerald-600";
  if (s === "failed" || s === "error") return "text-red-600";
  if (s === "running") return "text-blue-600";
  return "text-slate-500";
}

interface Props { repoId: string; jobId: string; onDone?: () => void; }

export default function IndexingProgress({ repoId, jobId, onDone }: Props) {
  const [status, setStatus] = useState<RepositoryStatusResponse | null>(null);
  const [skips,  setSkips]  = useState<RepositoryFileSkipResponse[]>([]);
  const [pollFailed, setPollFailed] = useState(false);
  const [showSkips, setShowSkips] = useState(false);
  const timer = useRef<ReturnType<typeof setInterval> | null>(null);
  const { showError } = useError();

  const poll = async () => {
    try {
      const s = await getRepositoryStatus(repoId);
      setStatus(s);
      if (s.latest_job && TERMINAL.has(s.latest_job.status)) {
        clearInterval(timer.current!);
        try { setSkips(await getRepositorySkips(repoId)); } catch { /* ok */ }
        onDone?.();
      }
    } catch (e: unknown) {
      const msg = e instanceof Error ? e.message : "Polling failed";
      showError("Couldn't load indexing status", msg);
      setPollFailed(true);
      clearInterval(timer.current!);
    }
  };

  useEffect(() => {
    poll();
    timer.current = setInterval(poll, POLL_MS);
    return () => clearInterval(timer.current!);
  // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [repoId, jobId]);

  if (pollFailed) return (
    <div className="flex items-center gap-2 text-sm text-slate-500 bg-white border border-slate-200 rounded-2xl px-4 py-3">
      <AlertTriangle className="w-4 h-4 shrink-0 text-slate-400" /> Status unavailable — see the alert for details.
    </div>
  );

  if (!status) return (
    <div className="flex items-center gap-2 text-sm text-slate-500 bg-white border border-slate-200 rounded-2xl px-4 py-3">
      <Loader2 className="w-4 h-4 animate-spin text-blue-500" /> Loading job status…
    </div>
  );

  const job       = status.latest_job;
  const jobStatus = job?.status ?? "queued";
  const done      = TERMINAL.has(jobStatus);

  return (
    <div className="bg-white border border-slate-200 rounded-2xl overflow-hidden shadow-sm">
      {/* Header */}
      <div className="flex items-center justify-between px-5 py-4 border-b border-slate-100">
        <div className="flex items-center gap-3">
          <JobIcon s={jobStatus} />
          <div>
            <p className="text-sm font-semibold text-slate-800">
              Indexing{" "}
              <span className={`${statusColor(jobStatus)} capitalize`}>{jobStatus}</span>
            </p>
            <p className="text-xs text-slate-400 font-mono mt-0.5">Job {jobId.slice(0,8)}…</p>
          </div>
        </div>
        {!done && (
          <span className="text-xs text-blue-600 bg-blue-50 border border-blue-100 px-2.5 py-1 rounded-full">
            Polling every {POLL_MS / 1000}s
          </span>
        )}
      </div>

      {/* Progress bar */}
      <div className="h-1 w-full bg-slate-100">
        {!done && <div className="h-full bg-blue-500 animate-pulse w-full" />}
        {jobStatus === "completed" && <div className="h-full bg-emerald-400 w-full" />}
        {(jobStatus === "failed" || jobStatus === "error") && <div className="h-full bg-red-400 w-full" />}
      </div>

      {/* Body */}
      <div className="px-5 py-4 space-y-3 text-sm">
        <div className="grid grid-cols-2 gap-2 text-xs">
          {[
            ["Repository", status.status],
            job?.started_at  ? ["Started",  new Date(job.started_at).toLocaleTimeString()]  : null,
            job?.finished_at ? ["Finished", new Date(job.finished_at).toLocaleTimeString()] : null,
            job?.attempt_count !== undefined ? ["Attempts", String(job.attempt_count)] : null,
          ].filter(Boolean).map(([k, v]) => (
            <div key={k} className="bg-slate-50 border border-slate-100 rounded-xl px-3 py-2">
              <p className="text-slate-400 mb-0.5">{k}</p>
              <p className="font-semibold text-slate-700 capitalize">{v}</p>
            </div>
          ))}
        </div>

        {job?.error_summary && (
          <div className="bg-red-50 border border-red-200 rounded-xl px-4 py-3">
            <p className="text-xs font-semibold text-red-700 mb-1">
              Error{job.failed_stage ? ` in ${job.failed_stage}` : ""}
            </p>
            <p className="text-xs text-red-600 font-mono whitespace-pre-wrap">{job.error_summary}</p>
          </div>
        )}

        {skips.length > 0 && (
          <div className="border border-amber-200 rounded-xl overflow-hidden">
            <button
              onClick={() => setShowSkips(p => !p)}
              className="flex items-center justify-between w-full px-4 py-2.5 bg-amber-50 text-left"
            >
              <span className="text-xs font-semibold text-amber-800">
                {skips.length} file{skips.length !== 1 ? "s" : ""} skipped
              </span>
              {showSkips
                ? <ChevronDown  className="w-3.5 h-3.5 text-amber-600" />
                : <ChevronRight className="w-3.5 h-3.5 text-amber-600" />}
            </button>
            {showSkips && (
              <ul className="divide-y divide-amber-100 max-h-48 overflow-y-auto">
                {skips.map(s => (
                  <li key={s.id} className="px-4 py-2 bg-white">
                    <p className="text-xs font-mono text-slate-700">{s.path}</p>
                    <p className="text-xs text-slate-400">{s.reason}</p>
                  </li>
                ))}
              </ul>
            )}
          </div>
        )}
      </div>
    </div>
  );
}
