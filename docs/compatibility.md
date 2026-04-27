# LLM Backend Compatibility

This matrix records what the Phase 1 + Phase 3 adapter family supports today.

| Backend | `LLM_PROFILE` | Native computer tool | Function tool | Vision | Stateful | Verification status |
|---|---|---:|---:|---:|---:|---|
| OpenAI Responses | `openai-native` | ✓ | ✓ | ✓ | ✓ (server) | Not yet verified; requires `LLM_API_KEY` |
| LM Studio | `lmstudio-responses` | ✗ | ✓ | model dependent | ✓ (server) | Experimental; preflight reachable, GUI E2E not yet verified |
| vLLM | `vllm-responses` | ✗ | ✓ | model dependent | ✓ (server) | Not yet verified |
| Ollama | `ollama-stateless` | ✗ | ✓ | model dependent | manual history | Not yet verified |
| Mock | `mock` | n/a | n/a | n/a | n/a | Supported; mock E2E passes without keys |

## Required env per profile

### `openai-native`

```bash
LLM_PROFILE=openai-native
LLM_BASE_URL=https://api.openai.com/v1
LLM_API_KEY=<sk-...>
LLM_MODEL=gpt-4.1
LLM_TOOL_MODE=openai_computer
LLM_STATE_MODE=server
```

### `lmstudio-responses`

```bash
LLM_PROFILE=lmstudio-responses
LLM_BASE_URL=http://host.docker.internal:1234/v1   # or your remote LM Studio URL
LLM_API_KEY=lm-studio
LLM_MODEL=ui-tars-local
LLM_TOOL_MODE=function_computer
LLM_STATE_MODE=server
```

LMStudio does **not** support OpenAI's native `computer` tool. Setting
`LLM_TOOL_MODE=openai_computer` with this profile is rejected by the
preflight (`/api/preflight`) and surfaced as a banner in the frontend.

### `vllm-responses`

Same shape as LM Studio with the vLLM `/v1/responses` endpoint and a vision-capable model.

### `ollama-stateless`

```bash
LLM_PROFILE=ollama-stateless
LLM_BASE_URL=http://host.docker.internal:11434/v1
LLM_API_KEY=ollama
LLM_MODEL=qwen-vl
LLM_TOOL_MODE=function_computer
LLM_STATE_MODE=manual
```

Bounded history (`LLM_HISTORY_WINDOW`, default 12) is replayed each turn instead of relying on `previous_response_id`.

### `mock`

```bash
LLM_PROFILE=mock
```

The mock adapter performs `screenshot` then sends a final `agent_message`. Use it to validate the event/sandbox pipeline without consuming credits.

## Current smoke evidence

- Mock E2E: `make e2e-mock` passes against the full API/sandbox/event/storage path.
- LM Studio Qwen: `/api/preflight` reaches the configured `/v1/responses` endpoint, but the real GUI task is not marked supported yet. The latest `example.com` E2E attempt hit an upstream 524 timeout before the first tool call.

## Profile aliases

`LLM_PROFILE` is normalized case-insensitively:

| Input | Stored value |
|---|---|
| `OpenAI`, `openai` | `openai-native` |
| `LMStudio`, `lm-studio`, `LM Studio` | `lmstudio-responses` |
| `vLLM`, `vllm` | `vllm-responses` |
| `Ollama`, `ollama` | `ollama-stateless` |

## Preflight checks

`GET /api/preflight` returns:

```json
{
  "profile": "lmstudio-responses",
  "model": "qwen3.6-35b-a3b-mlx",
  "base_url": "https://lmstudio.example",
  "tool_mode": "function_computer",
  "state_mode": "server",
  "overall": "ok|warning|error",
  "checks": [
    {"name": "tool_mode", "status": "ok", "detail": ""},
    {"name": "responses_reachable", "status": "ok", "detail": "reachable (200)"}
  ]
}
```

Front-end shows a banner when `overall != "ok"` so misconfigurations (missing API key, wrong tool mode for the profile, unreachable endpoint) surface immediately.
