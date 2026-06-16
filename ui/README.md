# SkinGraph UI

A demo frontend for the SkinGraph skincare-coach API — React + Vite +
TypeScript, deployed on **Vercel** against the **Railway**-hosted backend.
Three sections:

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
- **Live backend** (Railway): set it to the Railway public URL of the API
  service (e.g. `https://<your-app>.up.railway.app`).
- **AWS reference stack**: set it to the ALB endpoint from
  `terraform output api_endpoint`.

The backend allows browser origins via `CORS_ORIGINS` (defaults to the Vite dev
ports). When the UI is hosted elsewhere, add that origin to `CORS_ORIGINS` on
the server — e.g. set it to your Vercel deployment URL on Railway.

## Deploying to Vercel

This app is deployed on **Vercel**. With the Vercel project rooted at `ui/`:

- **Framework preset:** Vite — build command `npm run build`, output dir `dist`.
- **Environment variable:** set `VITE_API_BASE_URL` to the Railway API URL
  (Vite inlines it at build time, so redeploy after changing it).
- On the backend (Railway), add the resulting Vercel URL to `CORS_ORIGINS`.

## Scripts

- `npm run dev` — start the dev server
- `npm run build` — typecheck + production build into `dist/`
- `npm run preview` — serve the production build locally
- `npm run typecheck` — type-check without emitting
