# OpenCAU Agent

Local Manus-style desktop agent. The frontend chats with an LLM backend that drives an isolated Ubuntu desktop through GUI actions (`xdotool`, `xclip`, `scrot`) inside Docker. The user sees the live desktop via embedded noVNC and a streaming event log.

Current state: **Phase 0 + Phase 1 + Phase 2 + Phase 3 wired**. The agent loop is real (LLM → `computer` tool → action executor → screenshot → next turn) and supports OpenAI native `computer` tool, generic function-tool backends (LM Studio, vLLM), and a stateless variant (Ollama). A `mock` profile lets you exercise the full pipeline without a key.

## Run

```bash
cp .env.example .env
# edit .env to point at your LLM backend (see docs/compatibility.md)
docker compose up --build
```

Open <http://localhost:3000>.

`LLM_PROFILE=mock` (the default in `.env.example`) is a no-key smoke profile that captures a screenshot and replies with a final message; use it for first-run sanity checks.

## Profiles

| Profile | Notes |
|---|---|
| `openai-native` | OpenAI Responses API with native `computer` tool. Set `LLM_API_KEY` and `LLM_MODEL`. |
| `lmstudio-responses` | LM Studio Responses API with the custom `computer` function tool. |
| `vllm-responses` | vLLM Responses API with the custom function tool. |
| `ollama-stateless` | Ollama-style backend; rebuilds bounded history each turn. |
| `mock` | Local-only smoke profile, no API key required. |

`LLM_PROFILE` is case-insensitive; `LMStudio`, `OpenAI`, `vLLM`, and `Ollama` are accepted aliases. See `docs/compatibility.md` for the full matrix.

## Endpoints

- `GET /api/health` — backend + display + LLM profile snapshot.
- `GET /api/preflight` — adapter readiness checks (tool/state mode mismatch, API key, reachability).
- `POST /api/sessions` — create a sandbox session.
- `POST /api/sessions/{id}/messages` — send a user instruction; streams events over WebSocket.
- `POST /api/sessions/{id}/interrupt` — abort the running agent loop.
- `GET /ws/sessions/{id}/events` — WebSocket event stream (`agent_reasoning_summary`, `tool_call`, `action_executed`, `screenshot`, `task_status`, `warning`, `error`).
- `GET /vnc/sessions/{id}/...` — backend reverse-proxy to the per-session noVNC endpoint.

## Checks

```bash
make lint   # python -m compileall on backend + sandbox-controller
make test   # 64 backend + 5 sandbox-controller unit tests
make smoke  # docker compose config validation
```

## Security notes

- Sandbox VNC ports are not published to the host. The backend is the only ingress.
- Only `sandbox-controller` mounts the Docker socket.
- The agent has **no** shell-execution tool; everything goes through the GUI action helper (`agent_action.py`) inside the sandbox.
- Sandbox containers run as a non-root `agent` user with `cap_drop: ["ALL"]`, `no-new-privileges:true`, read-only root, tmpfs for `/tmp` `/run` `/home/agent`, and memory/CPU/pids limits.
- Screenshot binary data never travels through the WebSocket — the event stream carries URL + sha256 only.

See `docs/architecture.md`, `docs/compatibility.md`, `docs/security.md`, and `docs/troubleshooting.md` for more.
