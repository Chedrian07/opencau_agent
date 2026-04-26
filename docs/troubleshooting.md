# Troubleshooting

## Docker Socket Permission

The sandbox-controller needs access to `/var/run/docker.sock`. On Docker Desktop this usually works through the mounted socket. On Linux, ensure the Docker daemon socket is reachable by the container.

## Sandbox Image Missing

Run:

```bash
docker compose build sandbox-template
```

`docker compose up --build` also builds the sandbox image through the `sandbox-template` service.

## Preflight reports `tool_mode: error`

`lmstudio-responses` and `vllm-responses` cannot use OpenAI's native `computer` tool. Set `LLM_TOOL_MODE=function_computer` (or `LLM_PROFILE=mock` to bypass the LLM entirely).

## `type` action times out

Earlier builds used `xclip -selection clipboard` synchronously, which leaves `xclip` running as the X selection owner and blocks the parent process. `agent_action.py` now uses `xdotool type` for ASCII text and a detached `xclip` Popen + `Ctrl+V` paste for non-ASCII / long text. Rebuild the sandbox image (`docker compose build sandbox-template`) if you still see `ACTION_TIMEOUT` from `xclip`.

## `LLM_PROFILE=LMStudio` looks invalid

Profile names are normalized case-insensitively (see `docs/compatibility.md`). `LMStudio`, `lmstudio`, and `lm-studio` all map to `lmstudio-responses`. `OpenAI` maps to `openai-native`. `vLLM` maps to `vllm-responses`. `Ollama` maps to `ollama-stateless`.

## Sandbox image lacks `agent_action.py`

The Phase 1 helper script is added in `sandbox/Dockerfile`. If you upgraded the repo without rebuilding, run:

```bash
docker compose build sandbox-template
docker compose up -d --force-recreate sandbox-template
```

## Backend ignores `.env` changes

`docker-compose.yml` enumerates the env keys it forwards into the backend container. Newly-added `LLM_*` and agent settings need an entry there too. Restart with `docker compose up -d --force-recreate backend` after editing `docker-compose.yml`.
