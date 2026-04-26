"use client";

import {
  AlertTriangle,
  Bot,
  Camera,
  CheckCircle2,
  CircleAlert,
  MessageSquare,
  Monitor,
  MousePointerClick,
  Play,
  RefreshCw,
  Send,
  Square,
  Trash2,
  Wifi,
  WifiOff,
} from "lucide-react";
import { type FormEvent, type ReactElement, useEffect, useMemo, useState } from "react";

import {
  absoluteBackendUrl,
  backendUrl,
  createSession,
  deleteSession,
  eventsWsUrl,
  getHealth,
  interruptSession,
  parseAgentEvent,
  sendMessage,
  type AgentEvent,
  type HealthInfo,
  type SessionInfo,
  type TaskStatusEvent,
  vncUrl,
} from "@/lib/api";

type RequestState = "idle" | "loading";
type SocketState = "idle" | "connecting" | "connected" | "closed" | "error";

type LocalMessage = {
  id: string;
  sessionId: string;
  text: string;
  ts: number;
};

type TimelineItem =
  | {
      kind: "user";
      item: LocalMessage;
    }
  | {
      kind: "event";
      item: AgentEvent;
    };

function formatTime(ts: number): string {
  return new Date(ts * 1000).toLocaleTimeString([], {
    hour: "2-digit",
    minute: "2-digit",
    second: "2-digit",
  });
}

function taskProgress(task: TaskStatusEvent | null): string {
  if (!task?.step || !task.max_steps) {
    return "-";
  }
  return `${task.step}/${task.max_steps}`;
}

function actionName(action: Record<string, unknown>): string {
  return typeof action.type === "string" ? action.type : "action";
}

function renderEvent(event: AgentEvent): ReactElement {
  switch (event.type) {
    case "session_created":
      return (
        <article className="eventCard eventNeutral">
          <CheckCircle2 aria-hidden="true" size={17} />
          <div>
            <div className="eventMeta">Session {formatTime(event.ts)}</div>
            <strong>Session created</strong>
          </div>
        </article>
      );
    case "agent_reasoning_summary":
      return (
        <article className="eventCard eventInfo">
          <Bot aria-hidden="true" size={17} />
          <div>
            <div className="eventMeta">Summary {formatTime(event.ts)}</div>
            <p>{event.text}</p>
          </div>
        </article>
      );
    case "agent_message":
      return (
        <article className="eventCard eventMessage">
          <MessageSquare aria-hidden="true" size={17} />
          <div>
            <div className="eventMeta">Agent {formatTime(event.ts)}</div>
            <p>{event.text}</p>
          </div>
        </article>
      );
    case "tool_call": {
      const actions = Array.isArray(event.args.actions) ? event.args.actions : [];
      const labels = actions
        .map((action) => (typeof action.type === "string" ? action.type : "action"))
        .join(", ");
      return (
        <article className="eventCard eventTool">
          <MousePointerClick aria-hidden="true" size={17} />
          <div>
            <div className="eventMeta">Tool call {formatTime(event.ts)}</div>
            <strong>{event.tool}</strong>
            <p>{labels || "No actions"}</p>
          </div>
        </article>
      );
    }
    case "action_executed":
      return (
        <article className={event.status === "ok" ? "eventCard eventSuccess" : "eventCard eventError"}>
          {event.status === "ok" ? <CheckCircle2 aria-hidden="true" size={17} /> : <CircleAlert aria-hidden="true" size={17} />}
          <div>
            <div className="eventMeta">Action {formatTime(event.ts)}</div>
            <strong>{actionName(event.action)}</strong>
            <p>
              {event.status} · {event.duration_ms}ms
            </p>
            {event.message ? <p className="mono">{event.message}</p> : null}
          </div>
        </article>
      );
    case "screenshot":
      return (
        <article className="eventCard eventScreenshot">
          <Camera aria-hidden="true" size={17} />
          <div>
            <div className="eventMeta">Screenshot {formatTime(event.ts)}</div>
            <img src={absoluteBackendUrl(event.thumb_url)} alt="" />
            <p className="mono">{event.sha256.slice(0, 12)}</p>
          </div>
        </article>
      );
    case "task_status":
      return (
        <article className="eventCard eventNeutral">
          <Bot aria-hidden="true" size={17} />
          <div>
            <div className="eventMeta">Task {formatTime(event.ts)}</div>
            <strong>{event.label}</strong>
            <p>{event.state}</p>
          </div>
        </article>
      );
    case "warning":
      return (
        <article className="eventCard eventWarning">
          <AlertTriangle aria-hidden="true" size={17} />
          <div>
            <div className="eventMeta">Warning {formatTime(event.ts)}</div>
            <strong>{event.code}</strong>
            <p>{event.message}</p>
          </div>
        </article>
      );
    case "error":
      return (
        <article className="eventCard eventError">
          <CircleAlert aria-hidden="true" size={17} />
          <div>
            <div className="eventMeta">Error {formatTime(event.ts)}</div>
            <strong>{event.code}</strong>
            <p>{event.message}</p>
          </div>
        </article>
      );
  }
}

export default function Home() {
  const [health, setHealth] = useState<HealthInfo | null>(null);
  const [session, setSession] = useState<SessionInfo | null>(null);
  const [state, setState] = useState<RequestState>("idle");
  const [socketState, setSocketState] = useState<SocketState>("idle");
  const [events, setEvents] = useState<AgentEvent[]>([]);
  const [localMessages, setLocalMessages] = useState<LocalMessage[]>([]);
  const [draft, setDraft] = useState("");
  const [error, setError] = useState<string | null>(null);

  const sessionId = session?.session_id ?? null;
  const iframeUrl = useMemo(() => {
    return session?.status === "running" ? vncUrl(session.session_id) : null;
  }, [session]);

  const latestTask = useMemo(() => {
    return [...events].reverse().find((event): event is TaskStatusEvent => event.type === "task_status") ?? null;
  }, [events]);

  const timeline = useMemo<TimelineItem[]>(() => {
    const userItems: TimelineItem[] = localMessages.map((message) => ({ kind: "user", item: message }));
    const eventItems: TimelineItem[] = events.map((event) => ({ kind: "event", item: event }));
    return [...userItems, ...eventItems].sort((left, right) => {
      const leftTs = left.kind === "user" ? left.item.ts : left.item.ts;
      const rightTs = right.kind === "user" ? right.item.ts : right.item.ts;
      return leftTs - rightTs;
    });
  }, [events, localMessages]);

  async function refreshHealth() {
    setError(null);
    try {
      setHealth(await getHealth());
    } catch (err) {
      setError(err instanceof Error ? err.message : "Health check failed");
    }
  }

  async function handleCreateSession() {
    setState("loading");
    setError(null);
    setEvents([]);
    setLocalMessages([]);
    try {
      setSession(await createSession());
    } catch (err) {
      setError(err instanceof Error ? err.message : "Session creation failed");
    } finally {
      setState("idle");
    }
  }

  async function handleDeleteSession() {
    if (!session) {
      return;
    }
    setState("loading");
    setError(null);
    try {
      await deleteSession(session.session_id);
      setSession(null);
      setEvents([]);
      setLocalMessages([]);
      setSocketState("idle");
    } catch (err) {
      setError(err instanceof Error ? err.message : "Session deletion failed");
    } finally {
      setState("idle");
    }
  }

  async function handleInterrupt() {
    if (!session) {
      return;
    }
    setError(null);
    try {
      await interruptSession(session.session_id);
    } catch (err) {
      setError(err instanceof Error ? err.message : "Interrupt failed");
    }
  }

  async function handleSubmit(event: FormEvent<HTMLFormElement>) {
    event.preventDefault();
    if (!session || !draft.trim()) {
      return;
    }
    const text = draft.trim();
    setDraft("");
    setError(null);
    setLocalMessages((current) => [
      ...current,
      {
        id: crypto.randomUUID(),
        sessionId: session.session_id,
        text,
        ts: Date.now() / 1000,
      },
    ]);
    try {
      const response = await sendMessage(session.session_id, text);
      if (!response.accepted) {
        setError("Task is already running for this session");
      }
    } catch (err) {
      setError(err instanceof Error ? err.message : "Message send failed");
    }
  }

  useEffect(() => {
    void refreshHealth();
  }, []);

  useEffect(() => {
    if (!sessionId) {
      setSocketState("idle");
      return;
    }

    setSocketState("connecting");
    const socket = new WebSocket(eventsWsUrl(sessionId));

    socket.onopen = () => setSocketState("connected");
    socket.onclose = () => setSocketState("closed");
    socket.onerror = () => setSocketState("error");
    socket.onmessage = (message) => {
      try {
        const parsed = parseAgentEvent(JSON.parse(message.data) as unknown);
        if (!parsed) {
          return;
        }
        setEvents((current) => {
          if (current.some((event) => event.session_id === parsed.session_id && event.sequence === parsed.sequence)) {
            return current;
          }
          return [...current, parsed].slice(-200);
        });
      } catch {
        setSocketState("error");
      }
    };

    return () => {
      socket.close();
    };
  }, [sessionId]);

  return (
    <main className="shell">
      <header className="topbar">
        <div className="brand">
          <Monitor aria-hidden="true" size={22} />
          <div>
            <h1>OpenCAU Agent</h1>
            <p>{backendUrl}</p>
          </div>
        </div>
        <div className="actions">
          <button type="button" className="iconButton" onClick={refreshHealth} aria-label="Refresh health">
            <RefreshCw aria-hidden="true" size={18} />
          </button>
          <button type="button" className="primaryButton" onClick={handleCreateSession} disabled={state === "loading" || Boolean(session)}>
            <Play aria-hidden="true" size={18} />
            <span>Start</span>
          </button>
          <button type="button" className="iconButton" onClick={handleInterrupt} disabled={!session} aria-label="Interrupt task">
            <Square aria-hidden="true" size={18} />
          </button>
          <button type="button" className="iconButton danger" onClick={handleDeleteSession} disabled={state === "loading" || !session} aria-label="Delete session">
            <Trash2 aria-hidden="true" size={18} />
          </button>
        </div>
      </header>

      <section className="workspace">
        <aside className="sidePane">
          <section className="statusBand" aria-label="Session status">
            <div>
              <span>Backend</span>
              <strong>{health?.status ?? "unknown"}</strong>
            </div>
            <div>
              <span>Socket</span>
              <strong className={socketState === "connected" ? "okText" : undefined}>
                {socketState === "connected" ? <Wifi aria-hidden="true" size={14} /> : <WifiOff aria-hidden="true" size={14} />}
                {socketState}
              </strong>
            </div>
            <div>
              <span>Session</span>
              <strong>{session?.status ?? "none"}</strong>
            </div>
            <div>
              <span>Steps</span>
              <strong>{taskProgress(latestTask)}</strong>
            </div>
          </section>

          <form className="composer" onSubmit={handleSubmit}>
            <textarea value={draft} onChange={(event) => setDraft(event.target.value)} disabled={!session} rows={3} aria-label="Agent message" />
            <button type="submit" className="sendButton" disabled={!session || !draft.trim()}>
              <Send aria-hidden="true" size={17} />
              <span>Send</span>
            </button>
          </form>

          {error ? <div className="errorBox">{error}</div> : null}

          <section className="timeline" aria-label="Session events">
            {timeline.length === 0 ? (
              <div className="emptyPanel">
                <MessageSquare aria-hidden="true" size={28} />
                <span>No events</span>
              </div>
            ) : (
              timeline.map((item) =>
                item.kind === "user" ? (
                  <article className="userMessage" key={item.item.id}>
                    <div className="eventMeta">You {formatTime(item.item.ts)}</div>
                    <p>{item.item.text}</p>
                  </article>
                ) : (
                  <div key={`${item.item.session_id}-${item.item.sequence}`}>{renderEvent(item.item)}</div>
                ),
              )
            )}
          </section>
        </aside>

        <section className="desktopPane" aria-label="Live desktop">
          {iframeUrl ? (
            <iframe title="Sandbox desktop" src={iframeUrl} />
          ) : (
            <div className="emptyState">
              <Monitor aria-hidden="true" size={34} />
              <span>No active desktop session</span>
            </div>
          )}
        </section>
      </section>
    </main>
  );
}
