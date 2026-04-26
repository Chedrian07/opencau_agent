export type SessionInfo = {
  session_id: string;
  status: "created" | "running" | "stopped" | "missing";
  vnc_url: string | null;
  container_id: string | null;
};

export type HealthInfo = {
  status: string;
  display: {
    width: number;
    height: number;
    depth: number;
  };
  llm?: {
    profile: string;
    model: string;
    tool_mode: string;
    state_mode: string;
  };
  agent?: {
    max_steps: number;
    timeout_sec: number;
  };
};

export type PreflightCheck = {
  name: string;
  status: "ok" | "warning" | "error" | "skipped";
  detail: string;
};

export type PreflightReport = {
  profile: string;
  model: string;
  base_url: string;
  tool_mode: string;
  state_mode: string;
  overall: "ok" | "warning" | "error" | "skipped";
  checks: PreflightCheck[];
};

export type EventType =
  | "session_created"
  | "agent_reasoning_summary"
  | "agent_message"
  | "tool_call"
  | "action_executed"
  | "screenshot"
  | "task_status"
  | "warning"
  | "error";

type EventBase = {
  type: EventType;
  session_id: string;
  ts: number;
  sequence: number;
};

export type SessionCreatedEvent = EventBase & {
  type: "session_created";
};

export type AgentReasoningSummaryEvent = EventBase & {
  type: "agent_reasoning_summary";
  text: string;
};

export type AgentMessageEvent = EventBase & {
  type: "agent_message";
  text: string;
};

export type ToolCallEvent = EventBase & {
  type: "tool_call";
  tool: string;
  args: {
    actions?: Array<Record<string, unknown>>;
    [key: string]: unknown;
  };
};

export type ActionExecutedEvent = EventBase & {
  type: "action_executed";
  action: Record<string, unknown>;
  duration_ms: number;
  status: "ok" | "error";
  error_code?: string | null;
  message?: string | null;
};

export type ScreenshotEvent = EventBase & {
  type: "screenshot";
  url: string;
  thumb_url: string;
  sha256: string;
};

export type TaskStatusEvent = EventBase & {
  type: "task_status";
  label: string;
  state: "queued" | "running" | "done" | "error" | "interrupted";
  step?: number | null;
  max_steps?: number | null;
};

export type WarningEvent = EventBase & {
  type: "warning";
  code: string;
  message: string;
};

export type ErrorEvent = EventBase & {
  type: "error";
  code: string;
  message: string;
};

export type AgentEvent =
  | SessionCreatedEvent
  | AgentReasoningSummaryEvent
  | AgentMessageEvent
  | ToolCallEvent
  | ActionExecutedEvent
  | ScreenshotEvent
  | TaskStatusEvent
  | WarningEvent
  | ErrorEvent;

export const backendUrl =
  process.env.NEXT_PUBLIC_BACKEND_URL?.replace(/\/$/, "") ?? "http://localhost:8000";

async function parseJson<T>(response: Response): Promise<T> {
  if (!response.ok) {
    throw new Error(`Request failed with ${response.status}`);
  }
  return (await response.json()) as T;
}

export async function getHealth(): Promise<HealthInfo> {
  return parseJson<HealthInfo>(await fetch(`${backendUrl}/api/health`, { cache: "no-store" }));
}

export async function getPreflight(): Promise<PreflightReport> {
  return parseJson<PreflightReport>(await fetch(`${backendUrl}/api/preflight`, { cache: "no-store" }));
}

export async function createSession(): Promise<SessionInfo> {
  return parseJson<SessionInfo>(
    await fetch(`${backendUrl}/api/sessions`, {
      method: "POST",
      headers: { "content-type": "application/json" },
      body: JSON.stringify({}),
    }),
  );
}

export async function sendMessage(sessionId: string, text: string): Promise<{ accepted: boolean; session_id: string }> {
  return parseJson<{ accepted: boolean; session_id: string }>(
    await fetch(`${backendUrl}/api/sessions/${sessionId}/messages`, {
      method: "POST",
      headers: { "content-type": "application/json" },
      body: JSON.stringify({ text }),
    }),
  );
}

export async function interruptSession(sessionId: string): Promise<void> {
  const response = await fetch(`${backendUrl}/api/sessions/${sessionId}/interrupt`, {
    method: "POST",
  });
  if (!response.ok) {
    throw new Error(`Interrupt failed with ${response.status}`);
  }
}

export async function deleteSession(sessionId: string): Promise<void> {
  const response = await fetch(`${backendUrl}/api/sessions/${sessionId}`, {
    method: "DELETE",
  });
  if (!response.ok) {
    throw new Error(`Delete failed with ${response.status}`);
  }
}

export function vncUrl(sessionId: string): string {
  const path = `vnc/sessions/${sessionId}/websockify`;
  return `${backendUrl}/vnc/sessions/${sessionId}/vnc.html?autoconnect=true&resize=scale&path=${encodeURIComponent(path)}`;
}

export function absoluteBackendUrl(path: string): string {
  if (path.startsWith("http://") || path.startsWith("https://")) {
    return path;
  }
  return `${backendUrl}${path.startsWith("/") ? path : `/${path}`}`;
}

export function eventsWsUrl(sessionId: string): string {
  const url = new URL(backendUrl);
  url.protocol = url.protocol === "https:" ? "wss:" : "ws:";
  url.pathname = `/ws/sessions/${sessionId}/events`;
  url.search = "";
  return url.toString();
}

function isRecord(value: unknown): value is Record<string, unknown> {
  return typeof value === "object" && value !== null;
}

export function parseAgentEvent(value: unknown): AgentEvent | null {
  if (!isRecord(value) || typeof value.type !== "string") {
    return null;
  }
  if (typeof value.session_id !== "string" || typeof value.ts !== "number" || typeof value.sequence !== "number") {
    return null;
  }

  switch (value.type) {
    case "session_created":
      return value as SessionCreatedEvent;
    case "agent_reasoning_summary":
    case "agent_message":
      return typeof value.text === "string" ? (value as AgentEvent) : null;
    case "tool_call":
      return typeof value.tool === "string" && isRecord(value.args) ? (value as ToolCallEvent) : null;
    case "action_executed":
      return isRecord(value.action) && typeof value.duration_ms === "number" && (value.status === "ok" || value.status === "error")
        ? (value as ActionExecutedEvent)
        : null;
    case "screenshot":
      return typeof value.url === "string" && typeof value.thumb_url === "string" && typeof value.sha256 === "string"
        ? (value as ScreenshotEvent)
        : null;
    case "task_status":
      return typeof value.label === "string" && typeof value.state === "string" ? (value as TaskStatusEvent) : null;
    case "warning":
    case "error":
      return typeof value.code === "string" && typeof value.message === "string" ? (value as AgentEvent) : null;
    default:
      return null;
  }
}
