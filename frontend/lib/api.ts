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
};

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

export async function createSession(): Promise<SessionInfo> {
  return parseJson<SessionInfo>(
    await fetch(`${backendUrl}/api/sessions`, {
      method: "POST",
      headers: { "content-type": "application/json" },
      body: JSON.stringify({}),
    }),
  );
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
