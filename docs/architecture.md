# Architecture

Current Phase 0 shape:

```text
frontend -> backend -> sandbox-controller -> Docker Engine -> sandbox containers
                |
                +-> noVNC reverse proxy -> sandbox noVNC
```

Responsibilities:

- `frontend/`: session UI and backend iframe target.
- `backend/`: public REST API, noVNC reverse proxy, and session orchestration.
- `sandbox-controller/`: restricted Docker lifecycle and allowlisted smoke commands.
- `sandbox/`: Ubuntu desktop image and GUI utility scripts.

LLM adapters and agent loop code are intentionally not implemented in this Phase 0 slice.
