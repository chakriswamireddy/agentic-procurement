import React from 'react';
import { BrowserRouter, Navigate, Route, Routes } from 'react-router-dom';
import { AuthProvider } from './auth/AuthContext';
import { RequireAuth } from './auth/RequireAuth';
import { Layout } from './components/Layout';
import { ErrorBoundary } from './components/ErrorBoundary';

import { LoginPage } from './pages/LoginPage';
import { NewRequestPage } from './pages/NewRequestPage';
import { WorkflowPage } from './pages/WorkflowPage';
import { RequestPage } from './pages/RequestPage';
import { ApprovalInboxPage } from './pages/ApprovalInboxPage';
import { SuppliersPage } from './pages/SuppliersPage';

export const App: React.FC = () => {
  return (
    <ErrorBoundary>
      <AuthProvider>
        <BrowserRouter>
          <Layout>
            <Routes>
              <Route path="/login" element={<LoginPage />} />

              <Route
                path="/"
                element={<Navigate to="/requests/new" replace />}
              />

              <Route
                path="/requests/new"
                element={
                  <RequireAuth>
                    <NewRequestPage />
                  </RequireAuth>
                }
              />

              <Route
                path="/workflows/:threadId"
                element={
                  <RequireAuth>
                    <WorkflowPage />
                  </RequireAuth>
                }
              />

              <Route
                path="/requests/:requestId"
                element={
                  <RequireAuth>
                    <RequestPage />
                  </RequireAuth>
                }
              />

              <Route
                path="/approvals"
                element={
                  <RequireAuth allowedRoles={['approver', 'admin']}>
                    <ApprovalInboxPage />
                  </RequireAuth>
                }
              />

              <Route
                path="/workflows"
                element={
                  <RequireAuth>
                    <ApprovalInboxPage />
                  </RequireAuth>
                }
              />

              <Route
                path="/suppliers"
                element={
                  <RequireAuth>
                    <SuppliersPage />
                  </RequireAuth>
                }
              />

              <Route
                path="*"
                element={
                  <div style={{ textAlign: 'center', padding: '3rem 1rem' }}>
                    <h2 style={{ fontSize: '1.5rem', fontWeight: 700, color: '#111827' }}>
                      404 &mdash; Page Not Found
                    </h2>
                    <p style={{ color: '#6b7280', fontSize: '0.875rem', marginTop: '0.5rem' }}>
                      The requested route does not exist.
                    </p>
                    <Navigate to="/" replace />
                  </div>
                }
              />
            </Routes>
          </Layout>
        </BrowserRouter>
      </AuthProvider>
    </ErrorBoundary>
  );
};

export default App;
