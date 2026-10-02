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

## Guided demo

Select **Run the guided demo** in the frontend. It creates a deterministic local checklist mission. Its first content attempt is an explicitly labeled simulated tool failure; verification then requests human-approved recovery, which executes locally and is reverified. The fixture does not call Gemini or Groq.

Mission data and audit events are held in backend memory and are cleared when the backend restarts.
