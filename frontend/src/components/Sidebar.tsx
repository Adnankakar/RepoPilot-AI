import React from "react";
import { NavLink, useNavigate } from "react-router-dom";
import { GitBranch, LayoutDashboard, MessageSquare, LogOut } from "lucide-react";
import { useAuth } from "../context/AuthContext";

const links = [
  { to: "/", label: "Dashboard", icon: LayoutDashboard },
  { to: "/qa", label: "Q&A", icon: MessageSquare },
];

export default function Sidebar() {
  const { user, logout } = useAuth();
  const navigate = useNavigate();

  const handleLogout = () => {
    logout();
    navigate("/auth");
  };

  return (
    <aside className="w-64 min-h-screen bg-gray-900 flex flex-col border-r border-gray-800">
      {/* Brand */}
      <div className="flex items-center gap-3 px-6 py-5 border-b border-gray-800">
        <div className="bg-blue-600 p-2 rounded-lg">
          <GitBranch className="w-5 h-5 text-white" />
        </div>
        <span className="font-bold text-white text-lg">RepoPilot AI</span>
      </div>

      {/* Nav */}
      <nav className="flex-1 px-3 py-4 space-y-1">
        {links.map(({ to, label, icon: Icon }) => (
          <NavLink
            key={to}
            to={to}
            end={to === "/"}
            className={({ isActive }) =>
              `flex items-center gap-3 px-4 py-2.5 rounded-lg text-sm font-medium transition ${
                isActive
                  ? "bg-blue-600 text-white"
                  : "text-gray-400 hover:bg-gray-800 hover:text-white"
              }`
            }
          >
            <Icon className="w-4 h-4" />
            {label}
          </NavLink>
        ))}
      </nav>

      {/* User */}
      <div className="px-4 py-4 border-t border-gray-800">
        <div className="flex items-center justify-between">
          <div className="min-w-0">
            <p className="text-xs text-gray-500 truncate">{user?.email}</p>
            <p className="text-xs text-gray-600">{user?.role}</p>
          </div>
          <button
            onClick={handleLogout}
            title="Sign out"
            className="ml-2 p-2 text-gray-500 hover:text-red-400 hover:bg-gray-800 rounded-lg transition"
          >
            <LogOut className="w-4 h-4" />
          </button>
        </div>
      </div>
    </aside>
  );
}
