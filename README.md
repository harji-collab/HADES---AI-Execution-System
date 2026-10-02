# HADES

HADES (Human-AI Driven Execution System) turns a goal into a local mission contract, dependency-aware plan, tool execution, evidence, requirement verification, and approved recovery when needed.

## Requirements

- Python 3.10 or newer
- Node.js 20.19+ or 22.12+
- npm

Gemini and Groq credentials are optional. Planning and the guided demo run locally without provider credentials. Optional AI enhancement is disabled unless `HADES_AI_ENHANCEMENTS=true` is set.

## Setup

From the project root in PowerShell:

```powershell
py -3 -m venv backend\venv
backend\venv\Scripts\python.exe -m pip install -r backend\requirements.txt
```

Create `backend\.env` only if using optional AI providers:

```dotenv
GEMINI_API_KEY=your_gemini_key
GROQ_API_KEY=your_groq_key
HADES_AI_ENHANCEMENTS=false
```

Do not commit `.env` files. Provider keys stay on the backend.

Install frontend dependencies:

```powershell
cd frontend
npm install
```

## Run

Open two PowerShell terminals from the project root.

Backend:

```powershell
cd backend
.\venv\Scripts\python.exe -m uvicorn main:app --reload --host 127.0.0.1 --port 8000
```

Frontend:

```powershell
cd frontend
npm run dev -- --host 127.0.0.1 --port 5173
```

Open <http://127.0.0.1:5173>. The backend health endpoint is <http://127.0.0.1:8000/health>.

The frontend defaults to `http://127.0.0.1:8000` in Vite development mode. Set `VITE_API_URL` only when you need a different backend URL; production defaults to the same-origin `/api` path.

## Guided demo

Select **Run the guided demo** in the frontend. It creates a deterministic local checklist mission. Its first content attempt is an explicitly labeled simulated tool failure; verification then requests human-approved recovery, which executes locally and is reverified. The fixture does not call Gemini or Groq.

Mission data and audit events are held in backend memory and are cleared when the backend restarts.

## Deploy to Vercel

The root `vercel.json` defines two Vercel Services in one project: the Vite frontend from `frontend/` and the FastAPI backend from `backend/` (`main:app`). The `/api` and `/api/*` rewrites route to the backend while all other paths route to the frontend. Vercel preserves the `/api` prefix; the backend middleware maps those requests to the same handlers used by local development.

1. Push this repository to GitHub and import/connect it in Vercel.
2. Set the Vercel project's Root Directory to the repository root. In Build and Deployment settings, set the Framework Preset to **Services**. The frontend service detects Vite and uses its normal build configuration.
3. Add `GEMINI_API_KEY` and/or `GROQ_API_KEY` as Vercel environment variables if enabling the corresponding optional AI providers. `HADES_AI_ENHANCEMENTS` may be set to `true` to enable optional AI enhancement. Do not put credentials in `VITE_*` variables: those are bundled into browser code. The guided demo and local planning work without provider credentials.
4. Deploy. Both services share the deployment's origin; browser API requests use `/api`.

The backend's mission registry is process-local memory, not durable storage. Serverless instances can restart or vary between requests, so missions may disappear and a follow-up request can receive 404. Workspace scans and generated files use the function's temporary filesystem and are not retained as permanent storage. Streaming is returned as Server-Sent Events, subject to Vercel Function duration limits; the browser aborts long requests after 90 seconds. Vercel Services availability and limits depend on the project's Vercel account and current platform settings.

For a local Services-style integration, install the Vercel CLI and run `vercel dev -L` from the repository root. For deployment with the CLI, run `vercel` from the root to link/deploy, then `vercel --prod` for production. Alternatively, pushing to the connected GitHub repository triggers deployments.
