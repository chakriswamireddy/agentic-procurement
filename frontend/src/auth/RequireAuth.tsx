import React from 'react';
import { Navigate, useLocation } from 'react-router-dom';
import { useAuth } from './AuthContext';
import { Loading } from '../components/Loading';

interface RequireAuthProps {
  children: React.ReactNode;
  allowedRoles?: Array<'requester' | 'approver' | 'admin' | 'auditor'>;
}

export const RequireAuth: React.FC<RequireAuthProps> = ({ children, allowedRoles }) => {
  const { isAuthenticated, isLoading, user } = useAuth();
  const location = useLocation();

  if (isLoading) {
    return <Loading label="Verifying session credentials..." />;
  }

  if (!isAuthenticated) {
    return <Navigate to="/login" state={{ from: location }} replace />;
  }

  if (allowedRoles && user && !allowedRoles.includes(user.role)) {
    return (
      <div style={{ padding: '2rem', maxWidth: '600px', margin: '2rem auto', textAlign: 'center' }}>
        <h2>403 - Access Denied</h2>
        <p>Your current role (<strong>{user.role}</strong>) does not have permission to view this page.</p>
        <p>This action is governed by server-side authorization policies (POL-002).</p>
      </div>
    );
  }

  return <>{children}</>;
};
