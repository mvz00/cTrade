import { useEffect, useRef, useState, useCallback } from 'react';

const TOKEN_KEY = 'ctrade_token';
const RECONNECT_DELAY_MS = 3_000;

export interface WebSocketMessage {
  type: string;
  data: Record<string, unknown>;
}

interface UseWebSocketOptions {
  /** Event types to subscribe to. Empty/undefined = receive all events. */
  subscriptions?: string[];
  /** Callback fired for each incoming event. */
  onMessage?: (msg: WebSocketMessage) => void;
  /** Set to false to disable the connection entirely. */
  enabled?: boolean;
}

interface UseWebSocketReturn {
  connected: boolean;
  lastMessage: WebSocketMessage | null;
}

/**
 * React hook that connects to the cTrade WebSocket endpoint.
 *
 * - Auto-connects with JWT from localStorage.
 * - Sends subscription filter on connect.
 * - Auto-reconnects on disconnect (3s delay).
 */
export function useWebSocket(options: UseWebSocketOptions = {}): UseWebSocketReturn {
  const { subscriptions, onMessage, enabled = true } = options;
  const [connected, setConnected] = useState(false);
  const [lastMessage, setLastMessage] = useState<WebSocketMessage | null>(null);
  const wsRef = useRef<WebSocket | null>(null);
  const reconnectTimer = useRef<ReturnType<typeof setTimeout>>(undefined);
  const onMessageRef = useRef(onMessage);
  onMessageRef.current = onMessage;

  const connect = useCallback(() => {
    if (!enabled) return;

    const token = localStorage.getItem(TOKEN_KEY);
    const protocol = window.location.protocol === 'https:' ? 'wss:' : 'ws:';
    const host = window.location.host;
    const url = `${protocol}//${host}/api/v1/ws${token ? `?token=${token}` : ''}`;

    const ws = new WebSocket(url);
    wsRef.current = ws;

    ws.onopen = () => {
      setConnected(true);
      // Send subscription filter
      if (subscriptions && subscriptions.length > 0) {
        ws.send(JSON.stringify({ subscribe: subscriptions }));
      }
    };

    ws.onmessage = (event) => {
      try {
        const msg = JSON.parse(event.data) as WebSocketMessage;
        setLastMessage(msg);
        onMessageRef.current?.(msg);
      } catch {
        // Ignore non-JSON messages
      }
    };

    ws.onclose = () => {
      setConnected(false);
      wsRef.current = null;
      // Auto-reconnect
      if (enabled) {
        reconnectTimer.current = setTimeout(connect, RECONNECT_DELAY_MS);
      }
    };

    ws.onerror = () => {
      // onclose will fire after onerror — reconnect happens there
    };
  }, [enabled, subscriptions]);

  useEffect(() => {
    connect();
    return () => {
      clearTimeout(reconnectTimer.current);
      if (wsRef.current) {
        wsRef.current.onclose = null; // Prevent reconnect on intentional close
        wsRef.current.close();
        wsRef.current = null;
      }
      setConnected(false);
    };
  }, [connect]);

  return { connected, lastMessage };
}
