# Demo Script

This is the short path for validating the product from a clean checkout.

## No-key demo

1. Start the stack with the deterministic mock profile:

   ```bash
   make demo
   ```

2. Open <http://localhost:3000>.
3. Send one of the welcome prompts.
4. Confirm the UI shows:
   - a chat transcript with the user request and agent response
   - a live CUA desktop panel
   - a reasoning summary card
   - the latest screenshot preview
   - action and screenshot events in the activity timeline

For an automated version of the same path:

```bash
make demo-check
```

## Real model E2E

1. Configure `.env` for a verified profile from `docs/compatibility.md`.
2. Start the stack:

   ```bash
   docker compose up --build
   ```

3. Run a concrete browser task:

   ```bash
   E2E_PROMPT="Open Firefox and navigate to https://example.com." make e2e-task
   ```

4. Confirm the final event sequence contains `task_status=done`, or review the warning/error code.

## Operator Notes

- `REPEATED_ACTION` means the model sent the same normalized action repeatedly.
- `SCREEN_UNCHANGED` means visual GUI actions kept executing but screenshot hashes did not change.
- `AGENT_TIMEOUT` means the run exceeded `AGENT_TIMEOUT_SEC`.
- Use the settings panel in the frontend to check profile, tool mode, state mode, display, preflight checks, and storage settings without opening logs.
