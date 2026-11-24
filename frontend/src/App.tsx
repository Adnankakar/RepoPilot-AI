import React from "react";
import {
  BrowserRouter,
  Routes,
  Route,
  Navigate,
  Outlet,
} from "react-router-dom";
import { AuthProvider, useAuth } from "./context/AuthContext";
import { AlertProvider } from "./context/ErrorContext";
import Sidebar from "./components/Sidebar";
import LandingPage from "./pages/LandingPage";
import HowToUsePage from "./pages/HowToUsePage";
import AuthPage from "./pages/AuthPage";
import DashboardPage from "./pages/DashboardPage";
import QAPage from "./pages/QAPage";
import { Loader2 } from "lucide-react";

// Full-page spinner shown while the stored token is being verified on startup.
export function FullPageSpinner() {
  return (
    <div className="min-h-screen flex flex-col items-center justify-center bg-slate-50 gap-3">
      <Loader2 className="w-6 h-6 text-blue-600 animate-spin" />
      <p className="text-sm text-slate-400">Loading</p>
    </div>
  );
}

// Authenticated layout shell.
function AppShell() {
  return (
    <div className="flex min-h-screen bg-slate-50">
      <Sidebar />
      <main className="flex-1 min-h-screen overflow-y-auto">
        <Outlet />
      </main>
    </div>
  );
}

// ── Route guards ──────────────────────────────────────────────────────────────

// Only renders children when authenticated; otherwise spins then redirects.
function RequireAuth({ children }: { children: React.ReactNode }) {
  const { user, loading } = useAuth();
  if (loading) return <FullPageSpinner />;
  if (!user) return <Navigate to="/auth" replace />;
  return <>{children}</>;
}

// Auth page redirects logged-in users away. While loading, render the auth
// page itself rather than flashing a spinner first.
function AuthGuard({ children }: { children: React.ReactNode }) {
  const { user, loading } = useAuth();
  if (loading) return <>{children}</>;
  if (user) return <Navigate to="/dashboard" replace />;
  return <>{children}</>;
}

// Root "/" — dashboard if logged in, landing otherwise.
function RootRedirect() {
  const { user, loading } = useAuth();
  if (loading) return <FullPageSpinner />;
  return <Navigate to={user ? "/dashboard" : "/landing"} replace />;
}

// ── App ───────────────────────────────────────────────────────────────────────
export default function App() {
  return (
    <BrowserRouter>
      <AuthProvider>
        <AlertProvider>
          <Routes>
          {/* Root redirect */}
          <Route path="/" element={<RootRedirect />} />

          {/* Always-public pages */}
          <Route path="/landing"    element={<LandingPage />} />
          <Route path="/how-to-use" element={<HowToUsePage />} />

          {/* Auth — visible to guests, redirects logged-in users */}
          <Route
            path="/auth"
            element={
              <AuthGuard>
                <AuthPage />
              </AuthGuard>
            }
          />

          {/* Protected app — requires login */}
          <Route
            element={
              <RequireAuth>
                <AppShell />
              </RequireAuth>
            }
          >
            <Route path="/dashboard" element={<DashboardPage />} />
            <Route path="/qa"        element={<QAPage />} />
          </Route>

          {/* Catch-all */}
          <Route path="*" element={<Navigate to="/" replace />} />
          </Routes>
        </AlertProvider>
      </AuthProvider>
    </BrowserRouter>
  );
}
