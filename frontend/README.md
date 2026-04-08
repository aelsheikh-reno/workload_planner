# Frontend MVP Shell

This module is the minimal real frontend shell for the Capacity-Aware Execution Planner MVP.

## What it does
- renders real routes for `S01` through `S05`
- opens `D01` from `S01`
- opens `M01` from `S04`
- talks only to the real API Gateway / BFF transport surface
- keeps primary workflow entry and return actions screen-owned instead of relying on a global shortcut nav

## Local run
Fastest start:
1. From the repo root, run `./scripts/run_local_mvp.sh`
2. Open the printed frontend URL, usually `http://127.0.0.1:5173`

Manual start:
1. Start the seeded BFF transport server from the repo root:
   - `python3 -m services.api_gateway_bff.server`
2. In this `frontend/` directory, install dependencies if needed:
   - `npm install`
3. Start the frontend dev server:
   - `npm run dev`

The Vite dev server proxies `/api` and `/health` requests to the launched local BFF target. The launcher keeps the proxy aligned even when it has to move off the default `8000` port.

## Local seeded runtime
The default local BFF server mode is `local-demo`. It seeds canonical in-memory data so the shell is usable in browser:
- a saved normalized snapshot
- a completed planning run for `context::frontend-shell`
- a current review context for `S04`
- `S05` warning/trust data

Reset behavior:
- use the shell Reset button to clear frontend-held context
- stop and restart the BFF server to reset the seeded backend state

## Useful commands
- `npm test`
- `npm run build`
- `npm run preview`

## MVP note
The shell keeps a lightweight shared planning context across screens, but screen actions remain screen-owned. Where the current BFF surface is intentionally thin, the UI exposes localized continuation steps on the owning screen rather than a global debug workflow.
