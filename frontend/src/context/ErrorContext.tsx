import React, {
  createContext,
  useCallback,
  useContext,
  useEffect,
  useState,
} from "react";
import { createPortal } from "react-dom";
import {
  AlertTriangle, X, ShieldAlert, WifiOff, ServerCrash, Info,
} from "lucide-react";

// ── Types ─────────────────────────────────────────────────────────────────────
type Severity = "error" | "warning" | "info" | "success";

interface AlertState {
  title: string;
  detail?: string;
  icon?: React.ReactNode;
  severity: Severity;
}

interface AlertContextValue {
  /** Show an error popup centered on screen. */
  showError: (title: string, detail?: string, icon?: React.ReactNode) => void;
  /** Show a generic alert with full control over severity + icon. */
  alert: (opts: AlertState) => void;
  /** Dismiss the current alert. */
  dismiss: () => void;
}

const AlertContext = createContext<AlertContextValue | null>(null);

export function useError(): AlertContextValue {
  const ctx = useContext(AlertContext);
  if (!ctx) throw new Error("useError must be used within an <AlertProvider>");
  return ctx;
}

// ── Severity styling ─────────────────────────────────────────────────────────
const SEVERITY: Record<
  Severity,
  { iconBg: string; ring: string; bar: string; DefaultIcon: React.ElementType; iconColor: string }
> = {
  error:   { iconBg: "bg-red-50",     ring: "ring-red-200",     bar: "bg-red-500",     DefaultIcon: AlertTriangle, iconColor: "text-red-600" },
  warning: { iconBg: "bg-amber-50",   ring: "ring-amber-200",   bar: "bg-amber-500",   DefaultIcon: AlertTriangle, iconColor: "text-amber-600" },
  info:    { iconBg: "bg-blue-50",    ring: "ring-blue-200",    bar: "bg-blue-600",    DefaultIcon: Info,           iconColor: "text-blue-600" },
  success: { iconBg: "bg-emerald-50", ring: "ring-emerald-200", bar: "bg-emerald-500", DefaultIcon: AlertTriangle, iconColor: "text-emerald-600" },
};

// ── Provider ─────────────────────────────────────────────────────────────────
export function AlertProvider({ children }: { children: React.ReactNode }) {
  const [state, setState] = useState<AlertState | null>(null);

  const dismiss = useCallback(() => setState(null), []);
  const alert   = useCallback((opts: AlertState) => setState(opts), []);
  const showError = useCallback(
    (title: string, detail?: string, icon?: React.ReactNode) =>
      setState({ title, detail, icon, severity: "error" }),
    []
  );

  // Escape key closes the popup.
  useEffect(() => {
    if (!state) return;
    const h = (e: KeyboardEvent) => { if (e.key === "Escape") dismiss(); };
    window.addEventListener("keydown", h);
    return () => window.removeEventListener("keydown", h);
  }, [state, dismiss]);

  return (
    <AlertContext.Provider value={{ showError, alert, dismiss }}>
      {children}
      {state &&
        createPortal(
          <AlertModal state={state} onClose={dismiss} />,
          document.body
        )}
    </AlertContext.Provider>
  );
}

// ── Modal ─────────────────────────────────────────────────────────────────────
function AlertModal({ state, onClose }: { state: AlertState; onClose: () => void }) {
  const sev = SEVERITY[state.severity] ?? SEVERITY.error;
  const Icon = state.icon ? null : sev.DefaultIcon;

  return (
    <div
      className="alert-backdrop-in fixed inset-0 z-[100] flex items-center justify-center p-4 bg-slate-900/40"
      onClick={(e) => { if (e.target === e.currentTarget) onClose(); }}
    >
      <div
        role="alertdialog"
        aria-modal="true"
        aria-labelledby="alert-title"
        className="alert-pop-in relative w-full max-w-md bg-white rounded-xl shadow-xl overflow-hidden border border-slate-200"
      >
        {/* Top accent bar */}
        <div className={`h-1 w-full ${sev.bar}`} />

        {/* Close button */}
        <button
          onClick={onClose}
          aria-label="Close"
          className="absolute top-3.5 right-3.5 p-1.5 rounded-lg text-slate-400 hover:text-slate-700 hover:bg-slate-100 transition"
        >
          <X className="w-4 h-4" />
        </button>

        {/* Body */}
        <div className="px-7 pt-7 pb-2">
          <div className="flex items-start gap-4">
            <div className={`shrink-0 p-3 rounded-xl ring-1 ${sev.iconBg} ${sev.ring}`}>
              {state.icon ? state.icon : (Icon ? <Icon className={`w-6 h-6 ${sev.iconColor}`} /> : null)}
            </div>
            <div className="flex-1 min-w-0 pt-1">
              <h3 id="alert-title" className="text-lg font-semibold text-slate-900 tracking-tight">
                {state.title}
              </h3>
              {state.detail && (
                <p className="text-sm text-slate-500 mt-1.5 leading-relaxed break-words">
                  {state.detail}
                </p>
              )}
            </div>
          </div>
        </div>

        {/* Footer */}
        <div className="flex justify-end px-7 pb-6 pt-4">
          <button
            onClick={onClose}
            className="px-5 py-2.5 text-sm font-semibold text-white bg-slate-900 hover:bg-slate-800 rounded-lg transition"
          >
            Got it
          </button>
        </div>
      </div>
    </div>
  );
}
