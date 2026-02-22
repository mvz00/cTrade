import { useState, useRef, useEffect } from 'react';
import { useNavigate } from 'react-router-dom';
import { useAuth } from '@/contexts/AuthContext';
import { ROUTES } from '@/lib/constants';
import { Settings, LogOut } from 'lucide-react';

export function UserDropdown() {
  const { username, logout } = useAuth();
  const navigate = useNavigate();
  const [open, setOpen] = useState(false);
  const ref = useRef<HTMLDivElement>(null);

  const initial = (username ?? 'A')[0].toUpperCase();

  // Close on outside click
  useEffect(() => {
    if (!open) return;
    function handleClick(e: MouseEvent) {
      if (ref.current && !ref.current.contains(e.target as Node)) {
        setOpen(false);
      }
    }
    document.addEventListener('mousedown', handleClick);
    return () => document.removeEventListener('mousedown', handleClick);
  }, [open]);

  return (
    <div className="relative" ref={ref}>
      {/* Avatar trigger */}
      <button
        onClick={() => setOpen(!open)}
        className="w-8 h-8 rounded-full bg-gradient-to-br from-ct-accent to-ct-blue flex items-center justify-center text-sm font-semibold text-white hover:ring-2 hover:ring-ct-accent/30 transition-all"
      >
        {initial}
      </button>

      {/* Dropdown menu */}
      {open && (
        <div className="absolute right-0 top-full mt-2 w-56 bg-ct-bg-card border border-ct-border rounded-xl shadow-xl overflow-hidden z-50">
          {/* User info */}
          <div className="px-4 py-3 border-b border-ct-border">
            <p className="text-sm font-medium text-ct-text">{username || 'admin'}</p>
            <p className="text-xs text-ct-text-dim">Administrator</p>
          </div>

          {/* Menu items */}
          <div className="py-1">
            <button
              onClick={() => {
                setOpen(false);
                navigate(ROUTES.ACCOUNT);
              }}
              className="w-full flex items-center gap-3 px-4 py-2.5 text-sm text-ct-text-muted hover:text-ct-text hover:bg-ct-bg-hover transition-colors"
            >
              <Settings size={16} />
              Account Settings
            </button>
          </div>

          {/* Divider + Sign out */}
          <div className="border-t border-ct-border py-1">
            <button
              onClick={() => {
                setOpen(false);
                logout();
              }}
              className="w-full flex items-center gap-3 px-4 py-2.5 text-sm text-ct-red hover:bg-ct-red/10 transition-colors"
            >
              <LogOut size={16} />
              Sign Out
            </button>
          </div>
        </div>
      )}
    </div>
  );
}
