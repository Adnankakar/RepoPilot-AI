import React, { useEffect, useRef, useState } from "react";
import {
  getRepositoryStatus,
  getRepositorySkips,
  RepositoryStatusResponse,
  RepositoryFileSkipResponse,
} from "../api";
import {
  Loader2,
  CheckCircle2,
  XCircle,
  Clock,
  AlertTriangle,
  ChevronDown,
  ChevronRight,
} from "lucide-react";

const POLL_MS = 2500;

const TERMINAL = new Set(["completed", "failed", "error"]);

function statusColor(s: string) {
  if (s === "completed") return "text-green-600";
  if (s === "failed" || s === "error") return "text-red-600";
  if (s === "running") return "text-blue-600";
  return "text-gray-500";
}

function statusIcon(s: string) {
  if (s === "completed") return <CheckCircle2 className="w-5 h-5 text-green-500" />;
  if (s === "failed" || s === "error") return <XCircle className="w-5 h-5 text-red-500" />;
  if (s === "running") return <Loader2 className="w-5 h-5 text-blue-500 animate-spin" />;
  return <Clock className="w-5 h-5 text-gray-400" />;
}

interface Props {
  repoId: string;
  jobId: string;
  onDone?: () => void;
}

export default function IndexingProgress({ repoId, jobId, onDone }: Props) {
  const [status, setStatus] = useState<RepositoryStatusResponse | null>(null);
  const [skips, setSkips] = useState<RepositoryFileSkipResponse[]>([]);
  const [error, setError] = useState<string | null>(null);
  const [showSkips, setShowSkips] = useState(false);
  const timerRef = useRef<ReturnType<typeof setInterval> | null>(null);

  const fetchStatus = async () => {
    try {
      const s = await getRepositoryStatus(repoId);
      setStatus(s);
      if (s.latest_job && TERMINAL.has(s.latest_job.status)) {
        clearInterval(timerRef.current!);
        // Fetch skips when done
        try {
          const sk = await getRepositorySkips(repoId);
          setSkips(sk);
        } catch {
          /* non-fatal */
        }
        onDone?.();
      }
    } catch (err: unknown) {
      setError(err instanceof Error ? err.message : "Polling failed");
      clearInterval(timerRef.current!);
    }
  };

  useEffect(() => {
    fetchStatus();
    timerRef.current = setInterval(fetchStatus, POLL_MS);
    return () => clearInterval(timerRef.current!);
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [repoId, jobId]);

  if (error) {
    return (
      <div className="flex items-center gap-2 text-sm text-red-700 bg-red-50 border border-red-200 rounded-lg px-4 py-3">
        <AlertTriangle className="w-4 h-4 shrink-0" />
        Polling error: {error}
      </div>
    );
  }

  if (!status) {
    return (
      <div className="flex items-center gap-2 text-gray-500 text-sm">
        <Loader2 className="w-4 h-4 animate-spin" /> Loading job status…
      </div>
    );
  }

  const job = status.latest_job;
  const jobStatus = job?.status ?? "queued";
  const isTerminal = TERMINAL.has(jobStatus);

  return (
    <div className="border border-gray-200 rounded-xl overflow-hidden bg-white">
      {/* Header */}
      <div className="flex items-center justify-between px-5 py-4 border-b border-gray-100">
        <div className="flex items-center gap-3">
          {statusIcon(jobStatus)}
          <div>
            <p className="text-sm font-semibold text-gray-800">
              Indexing{" "}
              <span className={`${statusColor(jobStatus)} capitalize`}>{jobStatus}</span>
            </p>
            <p className="text-xs text-gray-400 font-mono mt-0.5">Job {jobId}</p>
          </div>
        </div>
        {!isTerminal && (
          <span className="text-xs text-blue-600 bg-blue-50 px-2 py-1 rounded-full">
            Polling every {POLL_MS / 1000}s
          </span>
        )}
      </div>

      {/* Progress bar (indeterminate while running) */}
      {!isTerminal && (
        <div className="h-1.5 bg-gray-100 w-full overflow-hidden">
          <div className="h-full bg-blue-500 animate-pulse w-full" />
        </div>
      )}
      {jobStatus === "completed" && <div className="h-1.5 bg-green-400 w-full" />}
      {(jobStatus === "failed" || jobStatus === "error") && (
        <div className="h-1.5 bg-red-400 w-full" />
      )}

      {/* Body */}
      <div className="px-5 py-4 space-y-3 text-sm text-gray-700">
        <div className="grid grid-cols-2 gap-2 text-xs">
          <div className="bg-gray-50 rounded-lg px-3 py-2">
            <p className="text-gray-400 mb-0.5">Repository status</p>
            <p className="font-semibold capitalize">{status.status}</p>
          </div>
          {job?.started_at && (
            <div className="bg-gray-50 rounded-lg px-3 py-2">
              <p className="text-gray-400 mb-0.5">Started</p>
              <p className="font-semibold">
                {new Date(job.started_at).toLocaleTimeString()}
              </p>
            </div>
          )}
          {job?.finished_at && (
            <div className="bg-gray-50 rounded-lg px-3 py-2">
              <p className="text-gray-400 mb-0.5">Finished</p>
              <p className="font-semibold">
                {new Date(job.finished_at).toLocaleTimeString()}
              </p>
            </div>
          )}
          {job?.attempt_count !== undefined && (
            <div className="bg-gray-50 rounded-lg px-3 py-2">
              <p className="text-gray-400 mb-0.5">Attempts</p>
              <p className="font-semibold">{job.attempt_count}</p>
            </div>
          )}
        </div>

        {/* Error */}
        {job?.error_summary && (
          <div className="bg-red-50 border border-red-200 rounded-lg px-4 py-3">
            <p className="text-xs font-semibold text-red-700 mb-1">
              Error{job.failed_stage ? ` in ${job.failed_stage}` : ""}
            </p>
            <p className="text-xs text-red-600 font-mono whitespace-pre-wrap">
              {job.error_summary}
            </p>
          </div>
        )}

        {/* Skipped files */}
        {skips.length > 0 && (
          <div className="border border-amber-200 rounded-lg overflow-hidden">
            <button
              onClick={() => setShowSkips((p) => !p)}
              className="flex items-center justify-between w-full px-4 py-2.5 bg-amber-50 text-left"
            >
              <span className="text-xs font-semibold text-amber-800">
                {skips.length} file{skips.length !== 1 ? "s" : ""} skipped
              </span>
              {showSkips ? (
                <ChevronDown className="w-3.5 h-3.5 text-amber-600" />
              ) : (
                <ChevronRight className="w-3.5 h-3.5 text-amber-600" />
              )}
            </button>
            {showSkips && (
              <ul className="divide-y divide-amber-100 max-h-48 overflow-y-auto">
                {skips.map((s) => (
                  <li key={s.id} className="px-4 py-2 bg-white">
                    <p className="text-xs font-mono text-gray-700">{s.path}</p>
                    <p className="text-xs text-gray-400">{s.reason}</p>
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
