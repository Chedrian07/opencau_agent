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

## Mock E2E fails before events appear

`make e2e-mock` expects the compose stack to be running and healthy:

```bash
docker compose up --build
```

Use `LLM_PROFILE=mock` for this smoke path. The script creates a real sandbox session, sends one message, waits for the terminal `task_status`, verifies a PNG screenshot URL, and deletes the session.

## Real profile E2E task

With a configured non-mock profile, use:

```bash
E2E_PROMPT="Open Firefox and navigate to https://example.com." make e2e-task
```

This uses the same REST API path as the frontend and deletes the session at the end. It fails if the agent reaches `error`/`interrupted` instead of `done`.

For browser-navigation prompts, the script also probes the sandbox's active window title through the restricted `active_window_title` smoke command. By default it accepts `Example Domain` as observed success, which catches cases where the page is visibly loaded but a slow local model has not produced its final message yet. Override with `E2E_EXPECT_WINDOW_TITLE=...`, or set it to an empty value to require only terminal `done`.

## Firefox opens a first-run or privacy tab

The sandbox creates a fresh Firefox profile in `/home/agent` on startup and applies `user.js` prefs plus distribution policies to suppress first-run surfaces. If Firefox starts with welcome/privacy pages again, rebuild and recreate the sandbox image:

```bash
docker compose up --build -d sandbox-template sandbox-controller backend
```

## Model clicks the blank desktop instead of Firefox

The desktop is intentionally empty and the home directory is mounted `noexec`, so desktop `.desktop` launchers are not a reliable open path. Browser tasks should use the trusted bottom-panel Firefox launcher. The agent loop now rewrites likely missed browser-launcher clicks, such as the lower blank desktop around `y=970` or the top-left Applications menu, into a single click on the panel launcher and emits `BROWSER_LAUNCHER_ASSIST`.

## Agent stops with `SCREEN_UNCHANGED`

The agent executed visual GUI actions, but the stored screenshot hash did not change for several consecutive steps. This usually means the model is clicking the wrong target, the desktop is blocked by a modal, or the selected local model is emitting malformed coordinates that normalize to safe but ineffective actions.

Open the frontend activity panel, inspect the latest screenshot and action marker, then retry with a more concrete instruction. If this happens often for one model/profile, document it as an experimental compatibility result in `docs/compatibility.md`.
