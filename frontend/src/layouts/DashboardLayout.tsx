import React, { useState } from 'react';
import { NavLink, Outlet, useNavigate } from 'react-router-dom';
import { useAuth } from '../hooks/useAuth';
import { useTheme } from '../context/ThemeContext';
import { 
  MessageSquare, 
  FileText, 
  User as UserIcon, 
  Settings as SettingsIcon, 
  Shield, 
  LogOut, 
  Menu, 
  X, 
  Sun, 
  Moon, 
  Cpu 
} from 'lucide-react';

export const DashboardLayout: React.FC = () => {
  const { user, logout } = useAuth();
  const { theme, toggleTheme } = useTheme();
  const [sidebarOpen, setSidebarOpen] = useState<boolean>(true);
  const navigate = useNavigate();

  const handleLogout = () => {
    logout();
    navigate('/');
  };

  const navItems = [
    { name: 'AI Chatbot', path: '/chat', icon: MessageSquare },
    { name: 'My Documents', path: '/dashboard', icon: FileText },
    { name: 'Preferences', path: '/settings', icon: SettingsIcon },
  ];

  if (user?.role === 'admin') {
    navItems.push({ name: 'Admin Dashboard', path: '/admin', icon: Shield });
  }

  return (
    <div className="min-h-screen flex bg-gray-50 text-gray-900 transition-colors duration-200 dark:bg-dark-bg dark:text-gray-100">
      
      {/* Mobile Sidebar Overlay */}
      {!sidebarOpen && (
        <div 
          className="fixed inset-0 z-40 bg-black/40 backdrop-blur-sm lg:hidden"
          onClick={() => setSidebarOpen(true)}
        />
      )}

      {/* Sidebar Navigation */}
      <aside 
        className={`fixed inset-y-0 left-0 z-50 flex flex-col w-64 bg-white dark:bg-dark-card border-r border-gray-200/50 dark:border-white/5 transition-transform duration-300 lg:static lg:translate-x-0 ${
          sidebarOpen ? 'translate-x-0' : '-translate-x-full'
        }`}
      >
        <div className="h-16 flex items-center justify-between px-6 border-b border-gray-200/50 dark:border-white/5">
          <NavLink to="/" className="flex items-center gap-2 font-display text-xl font-black tracking-tight text-gray-900 dark:text-white">
            <span>Vellum <span className="font-normal text-zinc-500 dark:text-zinc-400">Console</span></span>
          </NavLink>
          <button 
            onClick={() => setSidebarOpen(false)}
            className="p-1.5 rounded-lg lg:hidden hover:bg-gray-100 dark:hover:bg-gray-800"
          >
            <X className="w-5 h-5" />
          </button>
        </div>

        {/* Navigation Tabs */}
        <nav className="flex-grow p-4 space-y-1">
          {navItems.map((item) => {
            const Icon = item.icon;
            return (
              <NavLink
                key={item.path}
                to={item.path}
                className={({ isActive }) =>
                  `flex items-center gap-3 px-4 py-3 rounded-xl font-semibold transition-all duration-150 ${
                    isActive 
                      ? 'bg-zinc-950 text-white dark:bg-white dark:text-zinc-950 shadow-sm' 
                      : 'hover:bg-zinc-100 dark:hover:bg-zinc-800/60 text-zinc-600 dark:text-zinc-400 hover:text-zinc-950 dark:hover:text-white'
                  }`
                }
              >
                <Icon className="w-5 h-5" />
                <span>{item.name}</span>
              </NavLink>
            );
          })}
        </nav>

        {/* Sidebar User Identity */}
        <div className="p-4 border-t border-gray-200/50 dark:border-white/5 flex flex-col items-center gap-1.5 shrink-0 bg-zinc-50/50 dark:bg-zinc-900/10">
          <span className="text-xs font-bold text-zinc-900 dark:text-zinc-100 truncate max-w-[200px]" title={user?.email}>
            {user?.full_name || 'Vellum Admin'}
          </span>
          <span className="inline-flex items-center px-2.5 py-0.5 rounded-full text-[9px] font-bold uppercase tracking-wider bg-zinc-100 dark:bg-zinc-800 text-zinc-900 dark:text-zinc-200 border border-zinc-200/60 dark:border-zinc-700/60">
            {user?.role || 'Admin'}
          </span>
        </div>
      </aside>

      {/* Main Body */}
      <div className="flex-grow flex flex-col min-w-0">
        {/* Top Navbar */}
        <header className="h-16 border-b border-gray-200/50 dark:border-white/5 bg-white dark:bg-dark-card flex items-center justify-between px-6">
          <button 
            onClick={() => setSidebarOpen(true)}
            className="p-2 rounded-lg hover:bg-gray-100 dark:hover:bg-gray-800 lg:hidden"
          >
            <Menu className="w-5 h-5" />
          </button>

          <div className="flex-grow lg:flex-grow-0">
            <h1 className="font-display font-bold text-lg hidden md:block">Workspace Console</h1>
          </div>

          <div className="flex items-center gap-4">
            {/* Quick theme selector */}
            <button
              onClick={toggleTheme}
              className="p-2 rounded-lg hover:bg-gray-100 dark:hover:bg-gray-800 transition-colors"
              aria-label="Toggle theme"
            >
              {theme === 'dark' ? <Sun className="w-5 h-5 text-yellow-400" /> : <Moon className="w-5 h-5" />}
            </button>
            
            <div className="h-8 w-px bg-gray-200 dark:bg-dark-border" />
            
            <div className="flex items-center gap-2">
              <span className="text-sm font-medium text-gray-600 dark:text-gray-400">Status:</span>
              <span className="inline-flex items-center px-2.5 py-0.5 rounded-full text-xs font-semibold bg-emerald-100 text-emerald-800 dark:bg-emerald-950/40 dark:text-emerald-400">
                Connected
              </span>
            </div>
          </div>
        </header>

        {/* Content Outlet */}
        <main className="flex-grow overflow-auto p-6">
          <div className="max-w-7xl mx-auto h-full">
            <Outlet />
          </div>
        </main>
      </div>
    </div>
  );
};


