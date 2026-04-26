# Security Baseline

This project lets an LLM operate a desktop, so the sandbox must be treated as potentially dangerous.

## Current Baseline

- Sandbox VNC/noVNC ports are available only on the Docker network.
- The backend exposes `/vnc/sessions/{session_id}/...` as the user-facing noVNC path.
- The backend does not mount `/var/run/docker.sock`.
- Only `sandbox-controller` mounts `/var/run/docker.sock`.
- Sandbox containers are launched with:
  - non-root `agent` user from the sandbox image
  - `cap_drop: ["ALL"]`
  - `security_opt: ["no-new-privileges:true"]`
  - read-only root filesystem
  - tmpfs for `/tmp`, `/run`, `/var/tmp`, and `/home/agent`
  - memory, CPU, and pids limits
- `sandbox-controller` command execution is allowlist based and does not accept arbitrary shell commands.

## Documented Exception

The `sandbox-controller` service mounts the Docker socket. This is required in Phase 0 so it can create, inspect, execute allowlisted smoke operations in, and delete per-session sandbox containers.

Narrowing controls:

- The socket is not mounted in the backend or frontend.
- The controller is not published to a host port.
- The controller exposes only lifecycle and allowlisted command endpoints on the internal Docker network.
- Container names and labels are controlled by the controller.

Future hardening should evaluate a docker-socket proxy or a rootless Docker/user-namespace deployment profile.
