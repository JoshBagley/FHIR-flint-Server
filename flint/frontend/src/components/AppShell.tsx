import { NavLink, Link, Outlet } from 'react-router-dom';
import { Layers, Users, Building2, MessageSquare, Server, LogOut, UserCircle } from 'lucide-react';
import AppLogo from './AppLogo';
import { useAuth } from '../contexts/AuthContext';

const NAV_ITEMS = [
  { to: '/admin',       label: 'Administrative', icon: Building2 },
  { to: '/clinical',    label: 'Clinical',        icon: Users },
  { to: '/terminology', label: 'Terminology',     icon: Layers },
  { to: '/mcp-chat',   label: 'MCP Chat',        icon: MessageSquare },
  { to: '/system',     label: 'System',           icon: Server },
];

export default function AppShell() {
  const { authRequired, isAuthenticated, username, logout } = useAuth();
  return (
    <div className="flex h-screen bg-gray-50">
      {/* Sidebar */}
      <aside className="w-56 flex-shrink-0 bg-white border-r border-gray-200 flex flex-col">
        <Link to="/" className="flex items-center gap-2.5 px-4 py-4 border-b border-gray-100 hover:bg-gray-50 transition-colors">
          <AppLogo size={32} className="rounded-lg shadow-sm flex-shrink-0" />
          <div>
            <p className="text-sm font-bold text-gray-900 leading-tight">Flint</p>
            <p className="text-[10px] text-gray-400 uppercase tracking-wide">FHIR R4 Server</p>
          </div>
        </Link>
        <nav className="flex-1 px-2 py-3 space-y-0.5">
          {NAV_ITEMS.map(({ to, label, icon: Icon }) => (
            <NavLink
              key={to}
              to={to}
              className={({ isActive }) =>
                `flex items-center gap-2.5 px-3 py-2 rounded-lg text-sm font-medium transition-colors ${
                  isActive
                    ? 'bg-blue-50 text-blue-700'
                    : 'text-gray-600 hover:bg-gray-100 hover:text-gray-900'
                }`
              }
            >
              <Icon className="w-4 h-4 flex-shrink-0" />
              {label}
            </NavLink>
          ))}
        </nav>
        <div className="px-4 py-3 border-t border-gray-100 space-y-2">
          {authRequired && isAuthenticated && (
            <div className="flex items-center justify-between gap-2">
              <div className="flex items-center gap-1.5 min-w-0">
                <UserCircle className="w-4 h-4 flex-shrink-0 text-gray-400" />
                <p className="text-xs text-gray-600 truncate">{username ?? 'Signed in'}</p>
              </div>
              <button
                onClick={logout}
                title="Sign out"
                className="flex-shrink-0 text-gray-400 hover:text-gray-600 transition-colors"
              >
                <LogOut className="w-3.5 h-3.5" />
              </button>
            </div>
          )}
          <a
            href="/docs"
            target="_blank"
            rel="noreferrer"
            className="text-xs text-gray-400 hover:text-gray-600 transition-colors"
          >
            API Docs ↗
          </a>
        </div>
      </aside>

      {/* Main content */}
      <main className="flex-1 overflow-auto">
        <Outlet />
      </main>
    </div>
  );
}
