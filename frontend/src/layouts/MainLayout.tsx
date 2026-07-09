import React from 'react';
import { Link, Outlet, useNavigate } from 'react-router-dom';
import { useAuth } from '../hooks/useAuth';
import { useTheme } from '../context/ThemeContext';
import { Sun, Moon, Cpu, LogIn, LayoutDashboard } from 'lucide-react';

export const MainLayout: React.FC = () => {
  const { user } = useAuth();
  const { theme, toggleTheme } = useTheme();
  const navigate = useNavigate();

  return (
    <div className="min-h-screen flex flex-col bg-gray-50 text-gray-900 transition-colors duration-200 dark:bg-dark-bg dark:text-gray-100">
      {/* Sticky Header */}
      <header className="sticky top-0 z-50 glass border-b border-gray-200/50 dark:border-white/5 backdrop-blur-md">
        <div className="max-w-7xl mx-auto px-4 sm:px-6 lg:px-8 h-16 flex items-center justify-between">
          <Link to="/" className="flex items-center gap-2 font-display text-2xl font-bold tracking-tight text-brand-600 dark:text-brand-400">
            <Cpu className="w-8 h-8 animate-pulse text-brand-500" />
            <span>Aura<span className="text-gray-900 dark:text-white font-normal">RAG</span></span>
          </Link>

          {/* Navigation Links */}
          <nav className="hidden md:flex items-center gap-8 font-medium">
            <Link to="/features" className="hover:text-brand-500 transition-colors">Features</Link>
            <Link to="/pricing" className="hover:text-brand-500 transition-colors">Pricing</Link>
            <Link to="/docs" className="hover:text-brand-500 transition-colors">Documentation</Link>
          </nav>

          {/* Settings & Auth Buttons */}
          <div className="flex items-center gap-4">
            <button
              onClick={toggleTheme}
              className="p-2 rounded-lg bg-gray-100 hover:bg-gray-200 dark:bg-dark-card dark:hover:bg-gray-800 transition-colors"
              aria-label="Toggle theme"
            >
              {theme === 'dark' ? <Sun className="w-5 h-5 text-yellow-400" /> : <Moon className="w-5 h-5" />}
            </button>

            {user ? (
              <button
                onClick={() => navigate('/dashboard')}
                className="flex items-center gap-2 px-4 py-2 rounded-lg bg-brand-500 text-white font-medium hover:bg-brand-600 active:scale-95 transition-all shadow-md shadow-brand-500/20"
              >
                <LayoutDashboard className="w-4 h-4" />
                <span>Console</span>
              </button>
            ) : (
              <button
                onClick={() => navigate('/login')}
                className="flex items-center gap-2 px-4 py-2 rounded-lg border border-gray-300 dark:border-dark-border hover:bg-gray-100 dark:hover:bg-gray-800 font-medium transition-all"
              >
                <LogIn className="w-4 h-4" />
                <span>Sign In</span>
              </button>
            )}
          </div>
        </div>
      </header>

      {/* Main Content Area */}
      <main className="flex-grow">
        <Outlet />
      </main>

      {/* Modern Footer */}
      <footer className="border-t border-gray-200/50 dark:border-white/5 bg-gray-100 dark:bg-dark-card/30">
        <div className="max-w-7xl mx-auto px-4 sm:px-6 lg:px-8 py-12 flex flex-col md:flex-row items-center justify-between gap-6">
          <div className="flex items-center gap-2">
            <Cpu className="w-6 h-6 text-brand-500" />
            <span className="font-display font-bold text-lg">AuraRAG</span>
          </div>
          <p className="text-sm text-gray-500 dark:text-dark-muted">
            &copy; {new Date().getFullYear()} AuraRAG Inc. Production-ready Semantic Search Platform.
          </p>
          <div className="flex gap-6 text-sm text-gray-500 dark:text-dark-muted">
            <a href="#" className="hover:text-brand-500">Privacy Policy</a>
            <a href="#" className="hover:text-brand-500">Terms of Service</a>
            <a href="#" className="hover:text-brand-500">Contact Support</a>
          </div>
        </div>
      </footer>
    </div>
  );
};


