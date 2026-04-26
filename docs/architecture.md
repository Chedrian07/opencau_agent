# Architecture

```text
┌──────────────┐    REST/WS    ┌──────────────────────────────────────────┐
│ frontend      │ ◄────────────► │ backend                                  │
│ Next.js 16    │               │ FastAPI                                  │
│  · chat       │               │  · /api/sessions  /api/messages          │
│  · event log  │               │  · /api/preflight /api/health            │
│  · noVNC view │               │  · /ws/sessions/{id}/events              │
│  · interrupt  │               │  · /vnc/sessions/{id}/* (reverse proxy)  │
└──────────────┘               │                                          │
                                │  ┌──────────────────────────────────┐    │
                                │  │ AgentRuntime / AgentLoop         │    │
                                │  │  · LLMAdapter (factory by profile)│   │
                                │  │  · ActionExecutor                │    │
                                │  │  · ScreenshotStore               │    │
                                │  │  · SessionEventBroker            │    │
                                │  └────────────┬─────────────────────┘    │
                                └───────────────┼──────────────────────────┘
                                                │ internal HTTP
                                                ▼
                                ┌─────────────────────────────────────┐
                                │ sandbox-controller (Docker API)     │
                                │  · /sessions  /sessions/{id}/actions │
                                │  · screenshots/latest.png           │
                                │  · vnc/* reverse proxy              │
                                └────────────┬────────────────────────┘
                                             │ docker exec
                                             ▼
                                ┌─────────────────────────────────────┐
                                │ sandbox-{session_id}                │
                                │  Ubuntu 24.04 + Xvfb + Xfce + x11vnc│
                                │  noVNC + xdotool + xclip + scrot    │
                                │  /usr/local/bin/agent_action.py     │
                                └─────────────────────────────────────┘
```

## Responsibilities

- `frontend/`: Next.js 16 (Turbopack) chat + live VNC view, preflight banner, action cards.
- `backend/`: FastAPI public surface, agent loop orchestration, LLM adapters, screenshot proxy.
- `sandbox-controller/`: restricted Docker lifecycle and the JSON action endpoint that drives `agent_action.py` inside each sandbox.
- `sandbox/`: Ubuntu desktop image, X stack, and the `agent_action.py` helper that translates a single internal action into safe `xdotool`/`xclip`/`scrot` subprocess calls.

## LLM adapters

The adapter family is profile based, not protocol based:

| Profile | Adapter | Tool mode | State mode | When to use |
|---|---|---|---|---|
| `openai-native` | `OpenAIComputerAdapter` | `openai_computer` | `server` | OpenAI Responses API with native `computer` tool |
| `lmstudio-responses` / `vllm-responses` | `FunctionComputerAdapter` | `function_computer` | `server` | LM Studio / vLLM (Responses API + custom function tool) |
| `ollama-stateless` | `StatelessFunctionAdapter` | `function_computer` | `manual` | Ollama-style stateless backend (no `previous_response_id`) |
| `mock` | `MockComputerAdapter` | n/a | n/a | Local development or smoke testing without an API key |

The adapter is selected by `app.llm.factory.build_adapter(settings)`. The `AgentLoop` calls only the adapter interface (`create_initial_response` / `continue_after_actions` / `aclose`) and never branches on backend.

## Internal Action model

Defined in `app/schemas/actions.py`. Every external tool output (OpenAI native, function call, mock) normalizes into this single model before reaching `ActionExecutor`. Supported types: `screenshot`, `click`, `double_click`, `right_click`, `move`, `drag`, `type`, `keypress`, `scroll`, `wait`, `cursor_position`. Coordinates are validated against the configured `DISPLAY_WIDTH`/`DISPLAY_HEIGHT`.

## Event contract

WebSocket payloads live in `app/schemas/events.py`. Screenshots are referenced by URL + sha256 only — base64 payloads are never streamed. Reasoning is exposed as `agent_reasoning_summary` only; raw chain-of-thought is not surfaced.
