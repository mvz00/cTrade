import { useState, useRef, useEffect, useCallback } from 'react';
import { PageHeader } from '@/components/ui/PageHeader';
import { Card } from '@/components/ui/Card';
import { Badge } from '@/components/ui/Badge';
import { useWebSocket } from '@/api/hooks/useWebSocket';
import {
  ScrollText, Trash2, Pause, Play, Search, ChevronDown,
} from 'lucide-react';
import { cn } from '@/lib/cn';

interface LogEntry {
  id: number;
  timestamp: string;
  level: string;
  logger: string;
  message: string;
  module: string;
  func: string;
  lineno: number;
}

const MAX_ENTRIES = 500;

const LEVELS = ['DEBUG', 'INFO', 'WARNING', 'ERROR', 'CRITICAL'] as const;
type Level = (typeof LEVELS)[number];

const LEVEL_COLORS: Record<string, string> = {
  DEBUG: 'text-ct-text-dim',
  INFO: 'text-ct-blue',
  WARNING: 'text-ct-yellow',
  ERROR: 'text-ct-red',
  CRITICAL: 'text-ct-red font-bold',
};

const LEVEL_BADGE: Record<string, 'default' | 'info' | 'success' | 'warning' | 'danger'> = {
  DEBUG: 'default',
  INFO: 'info',
  WARNING: 'warning',
  ERROR: 'danger',
  CRITICAL: 'danger',
};

let nextId = 0;

export function LoggingPage() {
  const [entries, setEntries] = useState<LogEntry[]>([]);
  const [minLevel, setMinLevel] = useState<Level>('DEBUG');
  const [searchText, setSearchText] = useState('');
  const [paused, setPaused] = useState(false);
  const [autoScroll, setAutoScroll] = useState(true);
  const scrollRef = useRef<HTMLDivElement>(null);
  const pausedRef = useRef(paused);
  pausedRef.current = paused;

  const onMessage = useCallback((msg: { type: string; data: Record<string, unknown> }) => {
    if (msg.type !== 'log.entry') return;
    if (pausedRef.current) return;

    const d = msg.data as {
      timestamp: string;
      level: string;
      logger: string;
      message: string;
      module: string;
      func: string;
      lineno: number;
    };

    setEntries(prev => {
      const next = [...prev, { ...d, id: nextId++ }];
      return next.length > MAX_ENTRIES ? next.slice(next.length - MAX_ENTRIES) : next;
    });
  }, []);

  useWebSocket({
    subscriptions: ['log.entry'],
    onMessage,
  });

  // Auto-scroll to bottom when new entries arrive
  useEffect(() => {
    if (autoScroll && scrollRef.current) {
      scrollRef.current.scrollTop = scrollRef.current.scrollHeight;
    }
  }, [entries, autoScroll]);

  // Detect manual scroll to disable auto-scroll
  const handleScroll = useCallback(() => {
    if (!scrollRef.current) return;
    const { scrollTop, scrollHeight, clientHeight } = scrollRef.current;
    const atBottom = scrollHeight - scrollTop - clientHeight < 40;
    setAutoScroll(atBottom);
  }, []);

  const minLevelIdx = LEVELS.indexOf(minLevel);
  const filtered = entries.filter(e => {
    const levelIdx = LEVELS.indexOf(e.level as Level);
    if (levelIdx < minLevelIdx) return false;
    if (searchText) {
      const lower = searchText.toLowerCase();
      return (
        e.message.toLowerCase().includes(lower) ||
        e.logger.toLowerCase().includes(lower) ||
        e.module.toLowerCase().includes(lower)
      );
    }
    return true;
  });

  const counts = entries.reduce<Record<string, number>>((acc, e) => {
    acc[e.level] = (acc[e.level] || 0) + 1;
    return acc;
  }, {});

  function formatTime(iso: string) {
    try {
      const d = new Date(iso);
      const hms = d.toLocaleTimeString('en-AU', { hour12: false, hour: '2-digit', minute: '2-digit', second: '2-digit' });
      const ms = String(d.getMilliseconds()).padStart(3, '0');
      return `${hms}.${ms}`;
    } catch {
      return iso;
    }
  }

  return (
    <div className="flex flex-col h-[calc(100vh-7rem)]">
      <PageHeader
        title="Logging"
        description="Live stream of backend log entries"
        actions={
          <div className="flex items-center gap-2">
            <Badge variant={paused ? 'warning' : 'success'}>
              {paused ? 'Paused' : 'Live'}
            </Badge>
            <span className="text-xs text-ct-text-dim">{entries.length} entries</span>
          </div>
        }
      />

      {/* Controls */}
      <Card className="mb-4">
        <div className="flex flex-wrap items-center gap-3">
          {/* Level filter */}
          <div className="flex items-center gap-2">
            <label className="text-xs text-ct-text-muted">Level:</label>
            <div className="relative">
              <select
                value={minLevel}
                onChange={e => setMinLevel(e.target.value as Level)}
                className="bg-ct-bg border border-ct-border rounded-lg px-3 py-1.5 text-sm text-ct-text appearance-none pr-8"
              >
                {LEVELS.map(l => (
                  <option key={l} value={l}>{l}{counts[l] ? ` (${counts[l]})` : ''}</option>
                ))}
              </select>
              <ChevronDown size={14} className="absolute right-2 top-1/2 -translate-y-1/2 text-ct-text-dim pointer-events-none" />
            </div>
          </div>

          {/* Search */}
          <div className="relative flex-1 min-w-[200px]">
            <Search size={14} className="absolute left-3 top-1/2 -translate-y-1/2 text-ct-text-dim" />
            <input
              type="text"
              value={searchText}
              onChange={e => setSearchText(e.target.value)}
              placeholder="Filter by message, logger, or module..."
              className="w-full bg-ct-bg border border-ct-border rounded-lg pl-9 pr-3 py-1.5 text-sm text-ct-text placeholder:text-ct-text-dim"
            />
          </div>

          {/* Actions */}
          <button
            onClick={() => setPaused(!paused)}
            className={cn(
              'flex items-center gap-1.5 px-3 py-1.5 rounded-lg text-sm font-medium transition-colors',
              paused
                ? 'bg-ct-green/20 text-ct-green hover:bg-ct-green/30'
                : 'bg-ct-yellow/20 text-ct-yellow hover:bg-ct-yellow/30',
            )}
          >
            {paused ? <Play size={14} /> : <Pause size={14} />}
            {paused ? 'Resume' : 'Pause'}
          </button>

          <button
            onClick={() => { setEntries([]); nextId = 0; }}
            className="flex items-center gap-1.5 px-3 py-1.5 rounded-lg text-sm font-medium bg-ct-bg-hover text-ct-text-muted hover:text-ct-text transition-colors"
          >
            <Trash2 size={14} />
            Clear
          </button>
        </div>
      </Card>

      {/* Log entries */}
      <Card className="flex-1 min-h-0 !p-0">
        <div
          ref={scrollRef}
          onScroll={handleScroll}
          className="h-full overflow-y-auto overflow-x-auto font-mono text-xs"
        >
          {filtered.length === 0 ? (
            <div className="flex flex-col items-center justify-center h-full text-ct-text-dim py-12">
              <ScrollText size={40} className="mb-3" />
              <p className="text-sm">{entries.length === 0 ? 'Waiting for log entries...' : 'No entries match your filters'}</p>
              {entries.length === 0 && (
                <p className="text-xs mt-1">Log entries will appear here as the backend processes requests</p>
              )}
            </div>
          ) : (
            <table className="w-full">
              <thead className="sticky top-0 bg-ct-bg-card border-b border-ct-border">
                <tr className="text-ct-text-muted text-left">
                  <th className="px-3 py-2 font-medium whitespace-nowrap">Time</th>
                  <th className="px-3 py-2 font-medium whitespace-nowrap w-20">Level</th>
                  <th className="px-3 py-2 font-medium whitespace-nowrap">Logger</th>
                  <th className="px-3 py-2 font-medium">Message</th>
                </tr>
              </thead>
              <tbody>
                {filtered.map(entry => (
                  <tr
                    key={entry.id}
                    className={cn(
                      'border-b border-ct-border/30 hover:bg-ct-bg-hover/50',
                      entry.level === 'ERROR' && 'bg-ct-red/5',
                      entry.level === 'CRITICAL' && 'bg-ct-red/10',
                      entry.level === 'WARNING' && 'bg-ct-yellow/5',
                    )}
                  >
                    <td className="px-3 py-1.5 text-ct-text-dim whitespace-nowrap">
                      {formatTime(entry.timestamp)}
                    </td>
                    <td className="px-3 py-1.5 whitespace-nowrap">
                      <Badge variant={LEVEL_BADGE[entry.level] ?? 'default'}>
                        {entry.level}
                      </Badge>
                    </td>
                    <td className="px-3 py-1.5 text-ct-text-muted whitespace-nowrap max-w-[200px] truncate" title={entry.logger}>
                      {entry.logger}
                    </td>
                    <td className={cn('px-3 py-1.5 break-all', LEVEL_COLORS[entry.level] ?? 'text-ct-text')}>
                      {entry.message}
                      {entry.func && (
                        <span className="text-ct-text-dim ml-2">
                          ({entry.module}.{entry.func}:{entry.lineno})
                        </span>
                      )}
                    </td>
                  </tr>
                ))}
              </tbody>
            </table>
          )}
        </div>
      </Card>

      {/* Scroll indicator */}
      {!autoScroll && !paused && (
        <button
          onClick={() => {
            setAutoScroll(true);
            if (scrollRef.current) {
              scrollRef.current.scrollTop = scrollRef.current.scrollHeight;
            }
          }}
          className="fixed bottom-6 right-6 bg-ct-accent text-ct-bg px-4 py-2 rounded-full shadow-lg text-sm font-medium flex items-center gap-2 hover:bg-ct-accent/90 transition-colors z-10"
        >
          <ChevronDown size={16} />
          Scroll to latest
        </button>
      )}
    </div>
  );
}
