# OpenCAU Agent

Local Manus-style desktop agent scaffold.

Current implementation phase: **Phase 0 foundation**. This slice provides:

- Docker Compose service skeleton.
- FastAPI backend health, session lifecycle, and noVNC reverse-proxy routes.
- Restricted sandbox-controller API with Docker socket isolated to that service.
- Ubuntu desktop sandbox image with Xvfb, Xfce, x11vnc, noVNC, xdotool, and scrot.
- Minimal Next.js frontend that can create and delete a sandbox session.

## Run

```bash
cp .env.example .env
docker compose up --build
```

Open http://localhost:3000.

## Checks

```bash
make lint
make test
make smoke
```

`make smoke` currently validates Compose configuration. Full sandbox boot and GUI action smoke tests are the next Phase 0 slice.

## Security Notes

- Sandbox VNC ports are not published to the host.
- The backend does not mount the Docker socket.
- The sandbox-controller mounts the Docker socket and exposes only restricted sandbox lifecycle and allowlisted command endpoints.
- Sandbox containers run as a non-root user and use `cap_drop: ["ALL"]`, `no-new-privileges:true`, resource limits, and read-only root filesystems where practical.
