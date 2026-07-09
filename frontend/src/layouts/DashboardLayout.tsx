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
    { name: 'Account Profile', path: '/profile', icon: UserIcon },
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
          <NavLink to="/" className="flex items-center gap-2 font-display text-xl font-bold tracking-tight text-brand-600 dark:text-brand-400">
            <Cpu className="w-6 h-6 text-brand-500" />
            <span>Aura<span className="text-gray-900 dark:text-white font-normal">Console</span></span>
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
                  `flex items-center gap-3 px-4 py-3 rounded-xl font-medium transition-all duration-150 ${
                    isActive 
                      ? 'bg-brand-500 text-white shadow-md shadow-brand-500/20' 
                      : 'hover:bg-gray-100 dark:hover:bg-gray-800 text-gray-600 dark:text-gray-400 hover:text-gray-900 dark:hover:text-white'
                  }`
                }
              >
                <Icon className="w-5 h-5" />
                <span>{item.name}</span>
              </NavLink>
            );
          })}
        </nav>

        {/* User Block & Logout */}
        <div className="p-4 border-t border-gray-200/50 dark:border-white/5">
          <div className="flex items-center gap-3 px-2 py-3 mb-2">
            <div className="w-10 h-10 rounded-full bg-brand-100 dark:bg-brand-900/30 flex items-center justify-center font-display font-bold text-brand-600 dark:text-brand-400">
              {user?.full_name?.charAt(0).toUpperCase() || 'U'}
            </div>
            <div className="overflow-hidden">
              <h4 className="font-semibold text-sm truncate">{user?.full_name}</h4>
              <p className="text-xs text-gray-500 dark:text-dark-muted truncate capitalize">{user?.role}</p>
            </div>
          </div>
          <button
            onClick={handleLogout}
            className="w-full flex items-center gap-3 px-4 py-3 text-red-600 dark:text-red-400 hover:bg-red-50 dark:hover:bg-red-950/20 rounded-xl font-medium transition-colors"
          >
            <LogOut className="w-5 h-5" />
            <span>Sign Out</span>
          </button>
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


