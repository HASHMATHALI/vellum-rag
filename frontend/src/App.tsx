import React from 'react';
import { BrowserRouter, Routes, Route, Navigate } from 'react-router-dom';
import { AuthProvider } from './context/AuthContext';
import { useAuth } from './hooks/useAuth';
import { ThemeProvider } from './context/ThemeContext';
import { FluidCanvas } from './components/ui/FluidCanvas';

// Layouts
import { MainLayout } from './layouts/MainLayout';
import { DashboardLayout } from './layouts/DashboardLayout';

// Public Pages
import { LandingPage } from './pages/LandingPage';
import { FeaturesPage } from './pages/FeaturesPage';
import { DocsPage } from './pages/DocsPage';

// Auth Pages
import { LoginPage } from './pages/LoginPage';
import { SignupPage } from './pages/SignupPage';

// Authenticated Console Pages
import { Dashboard } from './pages/Dashboard';
import { ChatInterface } from './components/ChatInterface';
import { ProfilePage } from './pages/ProfilePage';
import { SettingsPage } from './pages/SettingsPage';
import { AdminPage } from './pages/AdminPage';

// --- Authentication Route Guards ---
const ProtectedRoute: React.FC<{ children: React.ReactNode }> = ({ children }) => {
  return <>{children}</>;
};

const AdminRoute: React.FC<{ children: React.ReactNode }> = ({ children }) => {
  const { user, loading } = useAuth();
  
  if (loading) {
    return (
      <div className="min-h-screen flex items-center justify-center bg-gray-50 dark:bg-dark-bg">
        <div className="animate-spin rounded-full h-8 w-8 border-b-2 border-brand-500" />
      </div>
    );
  }
  
  if (!user || user.role !== 'admin') {
    return <Navigate to="/dashboard" replace />;
  }
  
  return <>{children}</>;
};

// --- App Component Assembly ---
const AppContent: React.FC = () => {
  return (
    <BrowserRouter>
      <FluidCanvas />
      <Routes>
        
        {/* Public Pages Route Mapping */}
        <Route element={<MainLayout />}>
          <Route path="/" element={<LandingPage />} />
          <Route path="/features" element={<FeaturesPage />} />
          <Route path="/docs" element={<DocsPage />} />
        </Route>

        {/* Authentication Route Mapping */}
        <Route path="/login" element={<LoginPage />} />
        <Route path="/signup" element={<Navigate to="/dashboard" replace />} />

        {/* Authenticated Workspace Route Mapping */}
        <Route element={<ProtectedRoute><DashboardLayout /></ProtectedRoute>}>
          <Route path="/dashboard" element={<Dashboard />} />
          <Route path="/chat" element={<ChatInterface />} />
          <Route path="/profile" element={<ProfilePage />} />
          <Route path="/settings" element={<SettingsPage />} />
          
          {/* Admin Guard Route Mapping */}
          <Route path="/admin" element={<AdminRoute><AdminPage /></AdminRoute>} />
        </Route>

        {/* Fallback Redirection */}
        <Route path="*" element={<Navigate to="/" replace />} />

      </Routes>
    </BrowserRouter>
  );
};

export default function App() {
  return (
    <ThemeProvider>
      <AuthProvider>
        <AppContent />
      </AuthProvider>
    </ThemeProvider>
  );
}


