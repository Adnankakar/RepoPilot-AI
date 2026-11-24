import React from "react";
import { NavLink, useNavigate } from "react-router-dom";
import { GitBranch, LayoutDashboard, MessageSquare, LogOut } from "lucide-react";
import { useAuth } from "../context/AuthContext";

const NAV = [
  { to: "/dashboard", label: "Dashboard", icon: LayoutDashboard },
  { to: "/qa", label: "Q&A", icon: MessageSquare },
];

export default function Sidebar() {
  const { user, logout } = useAuth();
  const navigate = useNavigate();

  const handleLogout = () => {
    logout();
    navigate("/landing");
  };
  const initial = user?.email?.[0]?.toUpperCase() ?? "?";

  return (
    <aside className="w-60 shrink-0 min-h-screen bg-white flex flex-col border-r border-slate-200">
      {/* Brand */}
      <div className="flex items-center gap-2.5 px-5 h-16 border-b border-slate-200">
        <div className="bg-blue-600 p-2 rounded-lg shrink-0">
          <GitBranch className="w-4 h-4 text-white" />
        </div>
        <span className="font-semibold text-slate-900 text-sm tracking-tight">RepoPilot AI</span>
      </div>

      {/* Nav */}
      <nav className="flex-1 px-3 py-4 space-y-1">
        {NAV.map(({ to, label, icon: Icon }) => (
          <NavLink
            key={to}
            to={to}
            end
            className={({ isActive }) =>
              `flex items-center gap-3 px-3 py-2.5 rounded-lg text-sm font-medium transition-colors ${
                isActive
                  ? "bg-blue-50 text-blue-700"
                  : "text-slate-600 hover:bg-slate-100 hover:text-slate-900"
              }`
            }
          >
            <Icon className="w-4 h-4 shrink-0" />
            {label}
          </NavLink>
        ))}
      </nav>

      {/* User */}
      <div className="px-3 py-3 border-t border-slate-200">
        <div className="flex items-center gap-2.5 px-2">
          <div className="w-8 h-8 rounded-full bg-blue-100 flex items-center justify-center shrink-0">
            <span className="text-xs font-semibold text-blue-700">{initial}</span>
          </div>
          <div className="flex-1 min-w-0">
            <p className="text-xs text-slate-700 truncate leading-tight">{user?.email}</p>
            <p className="text-xs text-slate-400 capitalize leading-tight mt-0.5">{user?.role}</p>
          </div>
          <button
            onClick={handleLogout}
            title="Sign out"
            aria-label="Sign out"
            className="p-2 rounded-lg text-slate-400 hover:text-slate-700 hover:bg-slate-100 transition"
          >
            <LogOut className="w-4 h-4" />
          </button>
        </div>
      </div>
    </aside>
  );
}
