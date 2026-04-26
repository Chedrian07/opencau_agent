"use client";

import { Monitor, Play, RefreshCw, Trash2 } from "lucide-react";
import { useEffect, useMemo, useState } from "react";

import { backendUrl, createSession, deleteSession, getHealth, type HealthInfo, type SessionInfo, vncUrl } from "@/lib/api";

type RequestState = "idle" | "loading" | "error";

export default function Home() {
  const [health, setHealth] = useState<HealthInfo | null>(null);
  const [session, setSession] = useState<SessionInfo | null>(null);
  const [state, setState] = useState<RequestState>("idle");
  const [error, setError] = useState<string | null>(null);

  const iframeUrl = useMemo(() => {
    return session?.status === "running" ? vncUrl(session.session_id) : null;
  }, [session]);

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
    } catch (err) {
      setError(err instanceof Error ? err.message : "Session deletion failed");
    } finally {
      setState("idle");
    }
  }

  useEffect(() => {
    void refreshHealth();
  }, []);

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
          <button type="button" className="iconButton danger" onClick={handleDeleteSession} disabled={state === "loading" || !session} aria-label="Delete session">
            <Trash2 aria-hidden="true" size={18} />
          </button>
        </div>
      </header>

      <section className="workspace">
        <aside className="panel">
          <div className="statusGrid">
            <div>
              <span>Backend</span>
              <strong>{health?.status ?? "unknown"}</strong>
            </div>
            <div>
              <span>Display</span>
              <strong>
                {health ? `${health.display.width}x${health.display.height}` : "unknown"}
              </strong>
            </div>
            <div>
              <span>Session</span>
              <strong>{session?.status ?? "none"}</strong>
            </div>
            <div>
              <span>ID</span>
              <strong className="mono">{session?.session_id ?? "-"}</strong>
            </div>
          </div>
          {error ? <div className="errorBox">{error}</div> : null}
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
