# Troubleshooting

## Docker Socket Permission

The sandbox-controller needs access to `/var/run/docker.sock`. On Docker Desktop this usually works through the mounted socket. On Linux, ensure the Docker daemon socket is reachable by the container.

## Sandbox Image Missing

Run:

```bash
docker compose build sandbox-template
```

`docker compose up --build` also builds the sandbox image through the `sandbox-template` service.
