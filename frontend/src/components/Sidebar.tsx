import React from "react";
import { NavLink, useNavigate } from "react-router-dom";
import { GitBranch, LayoutDashboard, MessageSquare, LogOut } from "lucide-react";
import { useAuth } from "../context/AuthContext";

const NAV_LINKS = [
  { to: "/",   label: "Dashboard", icon: LayoutDashboard, end: true },
  { to: "/qa", label: "Q&A",       icon: MessageSquare,   end: false },
];

export default function Sidebar() {
  const { user, logout } = useAuth();
  const navigate = useNavigate();

  const handleLogout = () => {
    logout();
    navigate("/auth");
  };

  const initial = user?.email?.[0]?.toUpperCase() ?? "?";

  return (
    <aside className="w-60 min-h-screen bg-gray-900 flex flex-col border-r border-gray-800 shrink-0">

      {/* Brand */}
      <div className="flex items-center gap-3 px-5 py-5 border-b border-gray-800">
        <div className="bg-blue-600 p-2 rounded-xl shrink-0">
          <GitBranch className="w-4 h-4 text-white" />
        </div>
        <span className="font-bold text-white text-base tracking-tight">RepoPilot AI</span>
      </div>

      {/* Nav */}
      <nav className="flex-1 px-3 py-4 space-y-0.5">
        {NAV_LINKS.map(({ to, label, icon: Icon, end }) => (
          <NavLink
            key={to}
            to={to}
            end={end}
            className={({ isActive }) =>
              `flex items-center gap-3 px-3.5 py-2.5 rounded-lg text-sm font-medium transition-colors ${
                isActive
                  ? "bg-blue-600 text-white shadow-sm shadow-blue-900/50"
                  : "text-gray-400 hover:bg-gray-800 hover:text-gray-100"
              }`
            }
          >
            <Icon className="w-4 h-4 shrink-0" />
            {label}
          </NavLink>
        ))}
      </nav>

      {/* User footer */}
      <div className="px-3 py-4 border-t border-gray-800">
        <div className="flex items-center gap-2.5 px-2">
          {/* Avatar initial */}
          <div className="w-7 h-7 rounded-full bg-blue-800 flex items-center justify-center shrink-0">
            <span className="text-xs font-semibold text-blue-200">{initial}</span>
          </div>
          <div className="flex-1 min-w-0">
            <p className="text-xs text-gray-300 truncate">{user?.email}</p>
            <p className="text-xs text-gray-600 capitalize">{user?.role}</p>
          </div>
          <button
            onClick={handleLogout}
            title="Sign out"
            className="p-1.5 rounded-lg text-gray-600 hover:text-red-400 hover:bg-gray-800 transition"
          >
            <LogOut className="w-3.5 h-3.5" />
          </button>
        </div>
      </div>
    </aside>
  );
}
