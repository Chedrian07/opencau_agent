"use client";

import {
  Activity,
  AlertTriangle,
  Bot,
  BrainCircuit,
  Camera,
  CheckCircle2,
  CircleAlert,
  Cpu,
  ExternalLink,
  History,
  MessageSquare,
  Monitor,
  MousePointerClick,
  Plus,
  RefreshCw,
  Search,
  Send,
  Settings,
  Square,
  Trash2,
  Wifi,
  WifiOff,
} from "lucide-react";
import {
  type FormEvent,
  type KeyboardEvent,
  type ReactElement,
  useEffect,
  useMemo,
  useRef,
  useState,
} from "react";

import {
  absoluteBackendUrl,
  createSession,
  deleteSession,
  eventsWsUrl,
  getHealth,
  getPreflight,
  getSessionEvents,
  interruptSession,
  listSessions,
  parseAgentEvent,
  sendMessage,
  type AgentEvent,
  type HealthInfo,
  type PreflightReport,
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

type ChatItem =
  | {
      kind: "user";
      item: LocalMessage;
    }
  | {
      kind: "event";
      item: AgentEvent;
    };

const INACTIVE_TASK_STATES = new Set(["done", "error", "interrupted"]);
const RUNNING_TASK_STATES = new Set(["queued", "running"]);
const CHAT_EVENT_TYPES = new Set<AgentEvent["type"]>([
  "agent_reasoning_summary",
  "agent_message",
  "warning",
  "error",
]);

const SUGGESTIONS = [
  "Open Firefox and visit example.com",
  "Find the current desktop resolution",
  "Open a browser and search for OpenCAU",
  "Take a screenshot and summarize what is visible",
];

function formatTime(ts: number): string {
  return new Date(ts * 1000).toLocaleTimeString([], {
    hour: "2-digit",
    minute: "2-digit",
    second: "2-digit",
  });
}

function taskProgress(task: TaskStatusEvent | null, fallbackMax: number | null): string {
  const step = task?.step ?? null;
  const max = task?.max_steps ?? fallbackMax ?? null;
  if (step == null && max == null) {
    return "-";
  }
  if (step != null && max != null) {
    return `${step}/${max}`;
  }
  if (step != null) {
    return `${step}`;
  }
  return `0/${max ?? "-"}`;
}

function actionName(action: Record<string, unknown>): string {
  return typeof action.type === "string" ? action.type : "action";
}

function truncate(text: string, max: number): string {
  if (text.length <= max) {
    return text;
  }
  return `${text.slice(0, max - 1)}…`;
}

function asNumber(value: unknown): number | null {
  return typeof value === "number" && Number.isFinite(value) ? value : null;
}

function asString(value: unknown): string | null {
  return typeof value === "string" ? value : null;
}

function clampPercent(value: number, max: number): number {
  if (max <= 0) {
    return 0;
  }
  return Math.min(100, Math.max(0, (value / max) * 100));
}

function actionPoint(action: Record<string, unknown>): { x: number; y: number } | null {
  const x = asNumber(action.x);
  const y = asNumber(action.y);
  if (x != null && y != null) {
    return { x, y };
  }
  const path = Array.isArray(action.path) ? action.path : null;
  if (!path || path.length === 0) {
    return null;
  }
  const last = path[path.length - 1];
  if (!last || typeof last !== "object") {
    return null;
  }
  const px = asNumber((last as Record<string, unknown>).x);
  const py = asNumber((last as Record<string, unknown>).y);
  return px != null && py != null ? { x: px, y: py } : null;
}

function describeAction(action: Record<string, unknown>): string | null {
  const type = typeof action.type === "string" ? action.type : null;
  if (!type) {
    return null;
  }
  switch (type) {
    case "click":
    case "double_click":
    case "right_click":
    case "move": {
      const x = asNumber(action.x);
      const y = asNumber(action.y);
      const button = asString(action.button);
      if (x != null && y != null) {
        return button ? `(${x},${y}) ${button}` : `(${x},${y})`;
      }
      return null;
    }
    case "scroll": {
      const x = asNumber(action.x);
      const y = asNumber(action.y);
      const sx = asNumber(action.scroll_x);
      const sy = asNumber(action.scroll_y);
      const parts: string[] = [];
      if (x != null && y != null) {
        parts.push(`(${x},${y})`);
      }
      if (sx != null || sy != null) {
        parts.push(`Δ(${sx ?? 0},${sy ?? 0})`);
      }
      return parts.length > 0 ? parts.join(" ") : null;
    }
    case "drag": {
      const path = Array.isArray(action.path) ? action.path : null;
      if (!path || path.length === 0) {
        return null;
      }
      const points = path
        .map((point) => {
          if (point && typeof point === "object") {
            const px = asNumber((point as Record<string, unknown>).x);
            const py = asNumber((point as Record<string, unknown>).y);
            if (px != null && py != null) {
              return `(${px},${py})`;
            }
          }
          return null;
        })
        .filter((value): value is string => value != null);
      if (points.length === 0) {
        return null;
      }
      if (points.length <= 4) {
        return points.join(" → ");
      }
      return `${points[0]} → … → ${points[points.length - 1]} (${points.length} pts)`;
    }
    case "type": {
      const text = asString(action.text);
      if (text == null) {
        return null;
      }
      return `"${truncate(text, 64)}"`;
    }
    case "keypress": {
      const keys = Array.isArray(action.keys)
        ? action.keys.filter((key): key is string => typeof key === "string")
        : null;
      if (!keys || keys.length === 0) {
        const single = asString(action.keys);
        return single ? truncate(single, 64) : null;
      }
      return truncate(keys.join(" + "), 64);
    }
    case "wait": {
      const duration = asNumber(action.duration_ms);
      return duration != null ? `${duration}ms` : null;
    }
    default:
      return null;
  }
}

function eventIcon(event: AgentEvent): ReactElement {
  switch (event.type) {
    case "agent_reasoning_summary":
      return <BrainCircuit aria-hidden="true" size={16} />;
    case "agent_message":
      return <MessageSquare aria-hidden="true" size={16} />;
    case "tool_call":
    case "action_executed":
      return <MousePointerClick aria-hidden="true" size={16} />;
    case "screenshot":
      return <Camera aria-hidden="true" size={16} />;
    case "task_status":
      return <Activity aria-hidden="true" size={16} />;
    case "warning":
      return <AlertTriangle aria-hidden="true" size={16} />;
    case "error":
      return <CircleAlert aria-hidden="true" size={16} />;
    case "session_created":
      return <CheckCircle2 aria-hidden="true" size={16} />;
  }
}

function renderChatEvent(event: AgentEvent): ReactElement | null {
  switch (event.type) {
    case "agent_reasoning_summary":
      return (
        <article className="reasoningBubble">
          <BrainCircuit aria-hidden="true" size={17} />
          <div>
            <div className="bubbleMeta">Reasoning summary · {formatTime(event.ts)}</div>
            <p>{event.text}</p>
          </div>
        </article>
      );
    case "agent_message":
      return (
        <article className="messageRow assistantMessage">
          <div className="avatar assistantAvatar">
            <Bot aria-hidden="true" size={17} />
          </div>
          <div className="messageBubble">
            <div className="bubbleMeta">OpenCAU · {formatTime(event.ts)}</div>
            <p>{event.text}</p>
          </div>
        </article>
      );
    case "warning":
      return (
        <article className="inlineNotice warningNotice">
          <AlertTriangle aria-hidden="true" size={16} />
          <div>
            <strong>{event.code}</strong>
            <p>{event.message}</p>
          </div>
        </article>
      );
    case "error":
      return (
        <article className="inlineNotice errorNotice">
          <CircleAlert aria-hidden="true" size={16} />
          <div>
            <strong>{event.code}</strong>
            <p>{event.message}</p>
          </div>
        </article>
      );
    default:
      return null;
  }
}

function renderActivityEvent(event: AgentEvent): ReactElement {
  if (event.type === "tool_call") {
    const actions = Array.isArray(event.args.actions) ? event.args.actions : [];
    const labels = actions
      .map((action) => (typeof action.type === "string" ? action.type : "action"))
      .join(", ");
    return (
      <article className="activityItem eventTool">
        {eventIcon(event)}
        <div>
          <div className="activityMeta">Tool call · {formatTime(event.ts)}</div>
          <strong>{event.tool}</strong>
          <p>{labels || "No actions"}</p>
        </div>
      </article>
    );
  }

  if (event.type === "action_executed") {
    const detail = describeAction(event.action);
    return (
      <article className={event.status === "ok" ? "activityItem eventSuccess" : "activityItem eventError"}>
        {eventIcon(event)}
        <div>
          <div className="activityMeta">Action · {formatTime(event.ts)}</div>
          <strong>{actionName(event.action)}</strong>
          <p>
            {event.status} · {event.duration_ms}ms
          </p>
          {detail ? <p className="actionDetail">{detail}</p> : null}
          {event.message ? <p className="mono">{event.message}</p> : null}
        </div>
      </article>
    );
  }

  if (event.type === "screenshot") {
    return (
      <article className="activityItem eventScreenshot">
        {eventIcon(event)}
        <div>
          <div className="activityMeta">Screenshot · {formatTime(event.ts)}</div>
          <a
            className="screenshotLink"
            href={absoluteBackendUrl(event.url)}
            target="_blank"
            rel="noopener noreferrer"
            aria-label="Open full screenshot in new tab"
          >
            <img src={absoluteBackendUrl(event.thumb_url)} alt="" />
          </a>
          <p className="mono">{event.sha256.slice(0, 12)}</p>
        </div>
      </article>
    );
  }

  if (event.type === "task_status") {
    return (
      <article className="activityItem eventNeutral">
        {eventIcon(event)}
        <div>
          <div className="activityMeta">Task · {formatTime(event.ts)}</div>
          <strong>{event.label}</strong>
          <p>{event.state}</p>
        </div>
      </article>
    );
  }

  if (event.type === "session_created") {
    return (
      <article className="activityItem eventNeutral">
        {eventIcon(event)}
        <div>
          <div className="activityMeta">Session · {formatTime(event.ts)}</div>
          <strong>Session created</strong>
        </div>
      </article>
    );
  }

  if (event.type === "agent_reasoning_summary") {
    return (
      <article className="activityItem eventInfo">
        {eventIcon(event)}
        <div>
          <div className="activityMeta">Reasoning · {formatTime(event.ts)}</div>
          <p>{event.text}</p>
        </div>
      </article>
    );
  }

  if (event.type === "agent_message") {
    return (
      <article className="activityItem eventMessage">
        {eventIcon(event)}
        <div>
          <div className="activityMeta">Agent · {formatTime(event.ts)}</div>
          <p>{event.text}</p>
        </div>
      </article>
    );
  }

  return (
    <article className={event.type === "warning" ? "activityItem eventWarning" : "activityItem eventError"}>
      {eventIcon(event)}
      <div>
        <div className="activityMeta">{event.type === "warning" ? "Warning" : "Error"} · {formatTime(event.ts)}</div>
        <strong>{event.code}</strong>
        <p>{event.message}</p>
      </div>
    </article>
  );
}

export default function Home() {
  const [health, setHealth] = useState<HealthInfo | null>(null);
  const [preflight, setPreflight] = useState<PreflightReport | null>(null);
  const [session, setSession] = useState<SessionInfo | null>(null);
  const [sessions, setSessions] = useState<SessionInfo[]>([]);
  const [state, setState] = useState<RequestState>("idle");
  const [socketState, setSocketState] = useState<SocketState>("idle");
  const [bootNotice, setBootNotice] = useState<string | null>(null);
  const [events, setEvents] = useState<AgentEvent[]>([]);
  const [localMessages, setLocalMessages] = useState<LocalMessage[]>([]);
  const [draft, setDraft] = useState("");
  const [error, setError] = useState<string | null>(null);
  const [settingsOpen, setSettingsOpen] = useState(false);
  const chatRef = useRef<HTMLElement | null>(null);
  const activityRef = useRef<HTMLDivElement | null>(null);

  const sessionId = session?.session_id ?? null;
  const iframeUrl = useMemo(() => {
    return session?.status === "running" ? vncUrl(session.session_id) : null;
  }, [session]);

  const latestTask = useMemo(() => {
    return [...events].reverse().find((event): event is TaskStatusEvent => event.type === "task_status") ?? null;
  }, [events]);

  const latestReasoning = useMemo(() => {
    return [...events].reverse().find((event) => event.type === "agent_reasoning_summary") ?? null;
  }, [events]);

  const latestScreenshot = useMemo(() => {
    return [...events].reverse().find((event) => event.type === "screenshot") ?? null;
  }, [events]);

  const latestAction = useMemo(() => {
    return [...events].reverse().find((event) => event.type === "action_executed") ?? null;
  }, [events]);

  const latestActionPoint = useMemo(() => {
    return latestAction?.type === "action_executed" ? actionPoint(latestAction.action) : null;
  }, [latestAction]);

  const interruptEnabled = useMemo(() => {
    if (!session || !latestTask) {
      return false;
    }
    return !INACTIVE_TASK_STATES.has(latestTask.state);
  }, [session, latestTask]);

  const taskIsRunning = latestTask ? RUNNING_TASK_STATES.has(latestTask.state) : false;

  const profileLabel = useMemo(() => {
    const profile = health?.llm?.profile ?? preflight?.profile;
    const model = health?.llm?.model ?? preflight?.model;
    if (profile && model) {
      return `${profile} · ${model}`;
    }
    return profile || model || null;
  }, [health, preflight]);

  const toolMode = health?.llm?.tool_mode ?? preflight?.tool_mode ?? null;
  const stateMode = health?.llm?.state_mode ?? preflight?.state_mode ?? null;
  const maxSteps = health?.agent?.max_steps ?? null;
  const actionCount = events.filter((event) => event.type === "action_executed").length;
  const screenshotCount = events.filter((event) => event.type === "screenshot").length;

  const chatItems = useMemo<ChatItem[]>(() => {
    const userItems: ChatItem[] = localMessages
      .filter((message) => message.sessionId === sessionId)
      .map((message) => ({ kind: "user", item: message }));
    const eventItems: ChatItem[] = events
      .filter((event) => CHAT_EVENT_TYPES.has(event.type))
      .map((event) => ({ kind: "event", item: event }));
    return [...userItems, ...eventItems].sort((left, right) => {
      const leftTs = left.kind === "user" ? left.item.ts : left.item.ts;
      const rightTs = right.kind === "user" ? right.item.ts : right.item.ts;
      return leftTs - rightTs;
    });
  }, [events, localMessages]);

  const preflightIssues = useMemo(() => {
    if (!preflight || preflight.overall === "ok") {
      return null;
    }
    const failing = preflight.checks.filter((check) => check.status !== "ok");
    return failing.length > 0 ? failing : null;
  }, [preflight]);

  const runtimeRows = useMemo<Array<{ label: string; value: string }>>(() => {
    const display = health?.display
      ? `${health.display.width}×${health.display.height}×${health.display.depth}`
      : null;
    return [
      { label: "Profile", value: health?.llm?.profile ?? preflight?.profile ?? "-" },
      { label: "Model", value: health?.llm?.model ?? preflight?.model ?? "-" },
      { label: "Tool mode", value: health?.llm?.tool_mode ?? preflight?.tool_mode ?? "-" },
      { label: "State mode", value: health?.llm?.state_mode ?? preflight?.state_mode ?? "-" },
      { label: "Base URL", value: preflight?.base_url ?? "-" },
      { label: "Display", value: display ?? "-" },
      { label: "Max steps", value: health?.agent?.max_steps != null ? String(health.agent.max_steps) : "-" },
      { label: "Timeout", value: health?.agent?.timeout_sec != null ? `${health.agent.timeout_sec}s` : "-" },
      { label: "Session store", value: health?.storage?.session_backend ?? "-" },
      {
        label: "Screenshot retention",
        value: health?.storage?.screenshot_retention_hours != null ? `${health.storage.screenshot_retention_hours}h` : "-",
      },
    ];
  }, [health, preflight]);

  async function refreshHealth() {
    setError(null);
    try {
      const [nextHealth, nextPreflight] = await Promise.all([
        getHealth(),
        getPreflight().catch((err: unknown) => {
          // eslint-disable-next-line no-console
          console.warn("Preflight check failed", err);
          return null;
        }),
      ]);
      setHealth(nextHealth);
      if (nextPreflight) {
        setPreflight(nextPreflight);
      }
    } catch (err) {
      setError(err instanceof Error ? err.message : "Health check failed");
    }
  }

  async function refreshSessions(): Promise<SessionInfo[]> {
    const nextSessions = await listSessions();
    setSessions(nextSessions);
    return nextSessions;
  }

  async function restoreActiveSession() {
    try {
      const nextSessions = await refreshSessions();
      const runningSession = nextSessions.find((candidate) => candidate.status === "running") ?? null;
      if (!runningSession) {
        return;
      }
      setSession(runningSession);
      setBootNotice("Recovered the active computer session.");
      const restoredEvents = await getSessionEvents(runningSession.session_id);
      setEvents(restoredEvents);
    } catch (err) {
      setError(err instanceof Error ? err.message : "Session restore failed");
    }
  }

  async function handleSelectSession(nextSession: SessionInfo) {
    if (nextSession.session_id === sessionId) {
      return;
    }
    setState("loading");
    setError(null);
    try {
      setSession(nextSession);
      setBootNotice(`Loaded session ${truncate(nextSession.session_id, 12)}.`);
      setEvents(await getSessionEvents(nextSession.session_id));
    } catch (err) {
      setError(err instanceof Error ? err.message : "Session load failed");
    } finally {
      setState("idle");
    }
  }

  async function handleCreateSession() {
    setState("loading");
    setError(null);
    setBootNotice(null);
    setEvents([]);
    setLocalMessages([]);
    try {
      const created = await createSession();
      setSession(created);
      setSessions((current) => [created, ...current.filter((candidate) => candidate.session_id !== created.session_id)]);
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
      setSessions((current) => current.filter((candidate) => candidate.session_id !== session.session_id));
      setEvents([]);
      setLocalMessages([]);
      setBootNotice(null);
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

  async function submitText(text: string) {
    if (!text.trim() || state === "loading") {
      return;
    }
    if (taskIsRunning) {
      setError("A task is already running. Interrupt it or wait for it to finish.");
      return;
    }
    const cleanText = text.trim();
    setState("loading");
    setDraft("");
    setError(null);
    setBootNotice(null);
    try {
      let activeSession = session;
      if (!activeSession) {
        setEvents([]);
        const created = await createSession();
        activeSession = created;
        setSession(created);
        setSessions((current) => [created, ...current.filter((candidate) => candidate.session_id !== created.session_id)]);
      }
      setLocalMessages((current) => [
        ...current,
        {
          id: crypto.randomUUID(),
          sessionId: activeSession.session_id,
          text: cleanText,
          ts: Date.now() / 1000,
        },
      ]);
      const response = await sendMessage(activeSession.session_id, cleanText);
      if (!response.accepted) {
        setError("Task is already running for this session");
      }
    } catch (err) {
      setError(err instanceof Error ? err.message : "Message send failed");
    } finally {
      setState("idle");
    }
  }

  async function handleSubmit(event: FormEvent<HTMLFormElement>) {
    event.preventDefault();
    await submitText(draft);
  }

  function handleComposerKeyDown(event: KeyboardEvent<HTMLTextAreaElement>) {
    if ((event.metaKey || event.ctrlKey) && event.key === "Enter") {
      event.preventDefault();
      void submitText(draft);
    }
  }

  useEffect(() => {
    void refreshHealth();
    void restoreActiveSession();
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

  useEffect(() => {
    const node = chatRef.current;
    if (!node) {
      return;
    }
    node.scrollTop = node.scrollHeight;
  }, [chatItems.length]);

  useEffect(() => {
    const node = activityRef.current;
    if (!node) {
      return;
    }
    node.scrollTop = node.scrollHeight;
  }, [events.length]);

  return (
    <main className={session ? "appShell hasComputer" : "appShell"}>
      <aside className="navRail">
        <div className="navBrand">
          <div className="brandMark">OC</div>
          <div>
            <strong>OpenCAU</strong>
            <span>Agent</span>
          </div>
        </div>

        <button type="button" className="newTaskButton" onClick={handleCreateSession} disabled={state === "loading"}>
          <Plus aria-hidden="true" size={18} />
          <span>New task</span>
        </button>

        <div className="navSearch">
          <Search aria-hidden="true" size={16} />
          <span>{session ? truncate(session.session_id, 18) : "Ready to start"}</span>
        </div>

        <nav className="navMenu" aria-label="Workspace">
          <span className="navMenuItem active">
            <MessageSquare aria-hidden="true" size={17} />
            Chat
          </span>
          <span className={session ? "navMenuItem activeSoft" : "navMenuItem"}>
            <Monitor aria-hidden="true" size={17} />
            Computer
          </span>
          <span className="navMenuItem">
            <Activity aria-hidden="true" size={17} />
            Activity
          </span>
        </nav>

        <nav className="sessionList" aria-label="Recent sessions">
          <div className="sectionTitle">
            <History aria-hidden="true" size={14} />
            <span>Recent</span>
          </div>
          {sessions.length === 0 ? (
            <div className="sessionEmpty">No sessions yet</div>
          ) : (
            sessions.slice(0, 8).map((candidate) => (
              <button
                type="button"
                key={candidate.session_id}
                className={candidate.session_id === sessionId ? "sessionButton active" : "sessionButton"}
                onClick={() => void handleSelectSession(candidate)}
                disabled={state === "loading"}
                title={candidate.session_id}
              >
                <Monitor aria-hidden="true" size={15} />
                <span>
                  <strong>{truncate(candidate.session_id, 12)}</strong>
                  <em>{candidate.status}</em>
                </span>
              </button>
            ))
          )}
        </nav>

        <div className="navFooter">
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
            <span>Steps</span>
            <strong>{taskProgress(latestTask, maxSteps)}</strong>
          </div>
        </div>
      </aside>

      <section className="chatPane">
        <header className="chatHeader">
          <div className="modelBlock">
            <span className="eyebrow">Model</span>
            <strong>{profileLabel ?? "OpenCAU Agent"}</strong>
            <div className="runtimeMeta">
              {toolMode ? <span>{toolMode}</span> : null}
              {stateMode ? <span>{stateMode}</span> : null}
              {health?.storage?.session_backend ? <span>{health.storage.session_backend}</span> : null}
            </div>
          </div>
          <div className="headerActions">
            <button
              type="button"
              className={settingsOpen ? "iconButton active" : "iconButton"}
              onClick={() => setSettingsOpen((open) => !open)}
              aria-label="Runtime settings"
              title="Runtime settings"
            >
              <Settings aria-hidden="true" size={18} />
            </button>
            <button type="button" className="iconButton" onClick={refreshHealth} aria-label="Refresh health" title="Refresh health">
              <RefreshCw aria-hidden="true" size={18} />
            </button>
            <button
              type="button"
              className={interruptEnabled ? "iconButton active" : "iconButton"}
              onClick={handleInterrupt}
              disabled={!interruptEnabled}
              aria-label="Interrupt task"
              title={interruptEnabled ? "Interrupt running task" : "No task in flight"}
            >
              <Square aria-hidden="true" size={18} />
            </button>
            <button
              type="button"
              className="iconButton danger"
              onClick={handleDeleteSession}
              disabled={state === "loading" || !session}
              aria-label="Delete session"
              title="Delete session"
            >
              <Trash2 aria-hidden="true" size={18} />
            </button>
          </div>
        </header>

        {settingsOpen ? (
          <section className="settingsPanel" aria-label="Runtime settings">
            <div className="settingsGrid">
              {runtimeRows.map((row) => (
                <div key={row.label} className="settingsRow">
                  <span>{row.label}</span>
                  <strong>{row.value}</strong>
                </div>
              ))}
            </div>
            {preflight ? (
              <div className="preflightChecks" aria-label="Preflight checks">
                {preflight.checks.map((check) => (
                  <span key={check.name} className={`checkPill ${check.status}`}>
                    {check.name}: {check.status}
                  </span>
                ))}
              </div>
            ) : null}
          </section>
        ) : null}

        {preflightIssues ? (
          <div className={`preflightBanner ${preflight?.overall ?? "warning"}`} role="status">
            <strong>
              Preflight {preflight?.overall ?? "warning"}
              {preflight?.profile ? ` · ${preflight.profile}` : ""}
              {preflight?.model ? ` · ${preflight.model}` : ""}
            </strong>
            <ul>
              {preflightIssues.map((check) => (
                <li key={check.name}>
                  <span>{check.name}</span>
                  <span>{check.detail}</span>
                </li>
              ))}
            </ul>
          </div>
        ) : null}

        <div className={taskIsRunning ? "runStatus active" : "runStatus"} role="status">
          <span>{taskIsRunning ? "Running" : session ? "Ready" : "No computer attached"}</span>
          <strong>{latestTask?.label ?? bootNotice ?? "Type a task and OpenCAU will prepare the computer."}</strong>
        </div>

        <section className="chatFeed" aria-label="Conversation" ref={chatRef}>
          {chatItems.length === 0 ? (
            <div className="welcomeState">
              <div className="welcomeMark">
                <Cpu aria-hidden="true" size={34} />
              </div>
              <h1>What should OpenCAU do?</h1>
              <p>{session ? "The computer workspace is ready." : "Send a message and OpenCAU will start the computer."}</p>
              <div className="suggestionGrid">
                {SUGGESTIONS.map((suggestion) => (
                  <button
                    type="button"
                    key={suggestion}
                    className="suggestionButton"
                    onClick={() => void submitText(suggestion)}
                    disabled={state === "loading" || taskIsRunning}
                  >
                    {suggestion}
                  </button>
                ))}
              </div>
            </div>
          ) : (
            chatItems.map((item) => {
              if (item.kind === "user") {
                return (
                  <article className="messageRow userMessage" key={item.item.id}>
                    <div className="messageBubble">
                      <div className="bubbleMeta">You · {formatTime(item.item.ts)}</div>
                      <p>{item.item.text}</p>
                    </div>
                  </article>
                );
              }
              const rendered = renderChatEvent(item.item);
              return rendered ? <div key={`${item.item.session_id}-${item.item.sequence}`}>{rendered}</div> : null;
            })
          )}
        </section>

        {error ? <div className="errorBox">{error}</div> : null}

        <form className="chatComposer" onSubmit={handleSubmit}>
          <button
            type="button"
            className="composerPlus"
            onClick={handleCreateSession}
            disabled={state === "loading"}
            aria-label="Create session"
            title="Create session"
          >
            <Plus aria-hidden="true" size={19} />
          </button>
          <textarea
            value={draft}
            onChange={(event) => setDraft(event.target.value)}
            onKeyDown={handleComposerKeyDown}
            disabled={state === "loading"}
            rows={1}
            placeholder={session ? "Message OpenCAU" : "Ask anything. OpenCAU will start a computer automatically."}
            aria-label="Agent message"
          />
          <button type="submit" className="sendButton" disabled={!draft.trim() || state === "loading" || taskIsRunning} aria-label="Send message">
            <Send aria-hidden="true" size={18} />
          </button>
        </form>
      </section>

      {session ? (
        <aside className="computerDock" aria-label="Computer workspace">
          <header className="dockHeader">
            <div>
              <span className="eyebrow">CUA Computer</span>
              <strong>{latestTask?.label ?? session.status}</strong>
            </div>
            <div className="dockStats">
              <span>{actionCount} actions</span>
              <span>{screenshotCount} shots</span>
            </div>
          </header>

          <section className="desktopFrame" aria-label="Live desktop">
            {iframeUrl ? (
              <iframe title="Sandbox desktop" src={iframeUrl} />
            ) : (
              <div className="emptyDesktop">
                <Monitor aria-hidden="true" size={34} />
                <span>No active desktop session</span>
              </div>
            )}
          </section>

          <section className="screenshotPanel" aria-label="Latest screenshot">
            <div className="panelTitle">
              <Camera aria-hidden="true" size={16} />
              <span>Latest screen</span>
              {latestScreenshot && latestScreenshot.type === "screenshot" ? (
                <a
                  href={absoluteBackendUrl(latestScreenshot.url)}
                  target="_blank"
                  rel="noopener noreferrer"
                  className="panelLink"
                  aria-label="Open latest screenshot"
                >
                  <ExternalLink aria-hidden="true" size={13} />
                </a>
              ) : null}
            </div>
            {latestScreenshot && latestScreenshot.type === "screenshot" ? (
              <>
                <a className="shotViewport" href={absoluteBackendUrl(latestScreenshot.url)} target="_blank" rel="noopener noreferrer">
                  <img src={absoluteBackendUrl(latestScreenshot.url)} alt="Latest sandbox screenshot" />
                  {latestActionPoint ? (
                    <span
                      className="actionMarker"
                      style={{
                        left: `${clampPercent(latestActionPoint.x, health?.display.width ?? 1)}%`,
                        top: `${clampPercent(latestActionPoint.y, health?.display.height ?? 1)}%`,
                      }}
                      title={`Last action at ${latestActionPoint.x}, ${latestActionPoint.y}`}
                    />
                  ) : null}
                </a>
                <div className="shotMeta">
                  <span>{formatTime(latestScreenshot.ts)}</span>
                  <span>{latestScreenshot.sha256.slice(0, 12)}</span>
                  {latestAction?.type === "action_executed" ? <span>{actionName(latestAction.action)}</span> : null}
                </div>
              </>
            ) : (
              <div className="emptyShot">No screenshot yet</div>
            )}
          </section>

          <section className="reasoningPanel" aria-label="Reasoning summary">
            <div className="panelTitle">
              <BrainCircuit aria-hidden="true" size={16} />
              <span>Reasoning</span>
            </div>
            <p>
              {latestReasoning && latestReasoning.type === "agent_reasoning_summary"
                ? latestReasoning.text
                : "Waiting for the next model summary."}
            </p>
            {latestScreenshot && latestScreenshot.type === "screenshot" ? (
              <a href={absoluteBackendUrl(latestScreenshot.url)} target="_blank" rel="noopener noreferrer" className="latestShotLink">
                <Camera aria-hidden="true" size={14} />
                {latestScreenshot.sha256.slice(0, 12)}
              </a>
            ) : null}
          </section>

          <section className="activityPanel" aria-label="Run activity">
            <div className="panelTitle">
              <Activity aria-hidden="true" size={16} />
              <span>Activity</span>
            </div>
            <div className="activityList" ref={activityRef}>
              {events.length === 0 ? (
                <div className="emptyActivity">No activity yet</div>
              ) : (
                events.map((event) => <div key={`${event.session_id}-${event.sequence}`}>{renderActivityEvent(event)}</div>)
              )}
            </div>
          </section>
        </aside>
      ) : null}
    </main>
  );
}
