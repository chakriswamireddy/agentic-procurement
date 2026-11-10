import React from 'react';
import { Link, NavLink, useNavigate } from 'react-router-dom';
import { useAuth } from '../auth/AuthContext';

export const Layout: React.FC<{ children: React.ReactNode }> = ({ children }) => {
  const { user, logout, isAuthenticated } = useAuth();
  const navigate = useNavigate();

  const handleLogout = () => {
    logout();
    navigate('/login');
  };

  const navLinkStyle = ({ isActive }: { isActive: boolean }) => ({
    padding: '6px 12px',
    borderRadius: '6px',
    textDecoration: 'none',
    fontSize: '0.9rem',
    fontWeight: 500,
    color: isActive ? '#1d4ed8' : '#4b5563',
    backgroundColor: isActive ? '#eff6ff' : 'transparent',
  });

  return (
    <div style={{ minHeight: '100vh', display: 'flex', flexDirection: 'column', backgroundColor: '#f9fafb' }}>
      <header
        style={{
          backgroundColor: '#ffffff',
          borderBottom: '1px solid #e5e7eb',
          padding: '0.75rem 1.5rem',
          display: 'flex',
          alignItems: 'center',
          justifyContent: 'space-between',
          position: 'sticky',
          top: 0,
          zIndex: 10,
        }}
      >
        <div style={{ display: 'flex', alignItems: 'center', gap: '1.5rem' }}>
          <Link
            to="/"
            style={{
              textDecoration: 'none',
              fontWeight: 700,
              fontSize: '1.1rem',
              color: '#111827',
              display: 'flex',
              alignItems: 'center',
              gap: '6px',
            }}
          >
            <span>🛡️</span>
            <span>Agentic Procurement</span>
          </Link>

          {isAuthenticated && (
            <nav style={{ display: 'flex', gap: '0.5rem' }}>
              <NavLink to="/requests/new" style={navLinkStyle}>
                New Request
              </NavLink>
              <NavLink to="/approvals" style={navLinkStyle}>
                Approval Inbox
              </NavLink>
              <NavLink to="/suppliers" style={navLinkStyle}>
                Suppliers
              </NavLink>
              <NavLink to="/workflows" style={navLinkStyle}>
                Workflows
              </NavLink>
            </nav>
          )}
        </div>

        <div style={{ display: 'flex', alignItems: 'center', gap: '1rem' }}>
          {isAuthenticated && user ? (
            <div style={{ display: 'flex', alignItems: 'center', gap: '0.75rem' }}>
              <div style={{ textAlign: 'right' }}>
                <div style={{ fontSize: '0.85rem', fontWeight: 600, color: '#1f2937' }}>
                  {user.email}
                </div>
                <div style={{ fontSize: '0.75rem', color: '#6b7280' }}>
                  Role: <span style={{ textTransform: 'capitalize', fontWeight: 600, color: '#4b5563' }}>{user.role}</span>
                </div>
              </div>

              <button
                type="button"
                onClick={handleLogout}
                style={{
                  padding: '5px 10px',
                  backgroundColor: '#f3f4f6',
                  border: '1px solid #d1d5db',
                  borderRadius: '6px',
                  fontSize: '0.8rem',
                  cursor: 'pointer',
                  color: '#374151',
                }}
              >
                Sign Out
              </button>
            </div>
          ) : (
            <Link
              to="/login"
              style={{
                padding: '6px 14px',
                backgroundColor: '#2563eb',
                color: '#ffffff',
                textDecoration: 'none',
                borderRadius: '6px',
                fontSize: '0.875rem',
                fontWeight: 500,
              }}
            >
              Sign In
            </Link>
          )}
        </div>
      </header>

      {/* Demo environment banner */}
      <div
        style={{
          backgroundColor: '#eff6ff',
          borderBottom: '1px solid #dbeafe',
          padding: '4px 1rem',
          fontSize: '0.75rem',
          color: '#1e40af',
          textAlign: 'center',
        }}
      >
        <span>
          Reference Platform: POL-002 human approval enforced &middot; Deterministic candidate scoring &middot; Sandboxed MCP execution
        </span>
      </div>

      <main style={{ flex: 1, maxWidth: '1100px', width: '100%', margin: '0 auto', padding: '1.5rem 1rem' }}>
        {children}
      </main>

      <footer
        style={{
          padding: '1rem',
          textAlign: 'center',
          fontSize: '0.75rem',
          color: '#9ca3af',
          borderTop: '1px solid #e5e7eb',
          backgroundColor: '#ffffff',
        }}
      >
        Agentic Procurement System &middot; Phase 7 Reference Implementation &middot; Client acts as an observer; backend is the security boundary.
      </footer>
    </div>
  );
};
