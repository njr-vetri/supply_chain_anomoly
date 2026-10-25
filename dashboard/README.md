# Local dashboard

The dashboard is a local React + Vite + TypeScript + Tailwind application. It communicates only with the local FastAPI service. It does not use analytics, hosted APIs, remote fonts, or remote images.

## Install and run

From PowerShell:

```powershell
cd C:\Projects\supply-chain-risk-system\dashboard
npm install
Copy-Item .env.example .env
npm run dev
```

Vite defaults to `http://localhost:5173`. The API base URL defaults to `http://localhost:8000`; set `VITE_API_BASE_URL` in `dashboard/.env` only if the local API uses another URL. Start the backend separately using the steps in [RUN_LOCALLY.md](../docs/RUN_LOCALLY.md).

Open **Session credentials** in the sidebar and enter a local API key. The API key and UI role hint are kept in this browser tab's session storage. The API itself remains authoritative for permissions. No real API keys belong in `.env`, source code, or this README.

## Checks

```powershell
npm run lint
npm run typecheck
npm test
npm run build
```

Screen-by-screen instructions and current API limitations are in [UI_GUIDE.md](../docs/UI_GUIDE.md).
