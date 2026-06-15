# SkinGraph UI

A demo frontend for the SkinGraph skincare-coach API — React + Vite +
TypeScript. Three sections:

- **My Profile** — the active user's skin data (drives personalised coaching).
- **My Routine** — the user's saved product shelf; new scans are checked
  against it for conflicts and redundancy.
- **Check Product** — upload a label photo, run the LangGraph pipeline, and get
  a safety-checked, personalised recommendation.

## Prerequisites

- Node 18+ (tested on Node 24)
- The backend API running and reachable (see below)

## Setup

```bash
cd ui
npm install
cp .env.example .env   # then edit VITE_API_BASE_URL if needed
npm run dev
```

The dev server runs at http://localhost:5173.

## Pointing at the backend

The UI reads `VITE_API_BASE_URL` from `.env`:

- **Local backend** (default): `http://localhost:8000`
  Run the API with `uvicorn src.api.main:app --reload` or via
  `docker compose up`.
- **Deployed backend**: set it to the ALB endpoint from
  `terraform output api_endpoint`.

The backend allows browser origins via `CORS_ORIGINS` (defaults to the Vite dev
ports). Override it on the server if you host the UI elsewhere.

## Scripts

- `npm run dev` — start the dev server
- `npm run build` — typecheck + production build into `dist/`
- `npm run preview` — serve the production build locally
- `npm run typecheck` — type-check without emitting
