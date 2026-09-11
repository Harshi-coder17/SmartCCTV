import React from 'react';
import { BrowserRouter, Routes, Route, Navigate } from 'react-router-dom';
import { AuthProvider, useAuthContext } from './context/AuthContext';
import { WSProvider } from './context/WSContext';
import { Login } from './components/Login';
import { Layout } from './components/Layout';
import { Dashboard } from './components/Dashboard';
import { AlertsPage } from './components/AlertsPage';
import { EventsPage } from './components/EventsPage';
import { CameraGrid } from './components/CameraGrid';
import { GISMap } from './components/GISMap';
import { AuditLog } from './components/AuditLog';
import { AdminPanel } from './components/AdminPanel';
import { CameraDetailPage } from './components/CameraDetailPage';

const useAuth = useAuthContext;

function ProtectedRoute({ children }: { children: React.ReactNode }) {
  const { isAuthenticated, isLoading } = useAuth();
  if (isLoading) {
    return (
      <div style={{ display: 'flex', alignItems: 'center', justifyContent: 'center', height: '100vh', background: 'var(--bg-primary)' }}>
        <div className="loading-spinner" />
      </div>
    );
  }
  return isAuthenticated ? <>{children}</> : <Navigate to="/login" replace />;
}

function AdminRoute({ children }: { children: React.ReactNode }) {
  const { currentUser } = useAuth();
  if (!currentUser || !['admin', 'auditor'].includes(currentUser.role)) {
    return <Navigate to="/" replace />;
  }
  return <>{children}</>;
}

function AppRoutes() {
  const { isAuthenticated } = useAuth();

  return (
    <Routes>
      <Route
        path="/login"
        element={isAuthenticated ? <Navigate to="/" replace /> : <Login />}
      />
      <Route
        path="/*"
        element={
          <ProtectedRoute>
            <WSProvider>
              <Layout>
                <Routes>
                  <Route path="/" element={<Dashboard />} />
                  <Route path="/cameras" element={<CameraGrid />} />
                  <Route path="/cameras/:id" element={<CameraDetailPage />} />
                  <Route path="/alerts" element={<AlertsPage />} />
                  <Route path="/events" element={<EventsPage />} />
                  <Route path="/map" element={<GISMap />} />
                  <Route
                    path="/audit"
                    element={
                      <AdminRoute>
                        <AuditLog />
                      </AdminRoute>
                    }
                  />
                  <Route
                    path="/admin"
                    element={
                      <AdminRoute>
                        <AdminPanel />
                      </AdminRoute>
                    }
                  />
                  <Route path="*" element={<Navigate to="/" replace />} />
                </Routes>
              </Layout>
            </WSProvider>
          </ProtectedRoute>
        }
      />
    </Routes>
  );
}

export default function App() {
  return (
    <BrowserRouter>
      <AuthProvider>
        <AppRoutes />
      </AuthProvider>
    </BrowserRouter>
  );
}
