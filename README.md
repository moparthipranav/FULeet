# FLeet

FLeet is a coding-problem platform with a FastAPI backend and React frontend. The backend uses PostgreSQL for persistent data, Redis for drafts and interview state, and a Piston-compatible execution service for running submitted code.

## Requirements

- Python 3.13 or newer
- Node.js and npm
- Docker Desktop (for local PostgreSQL and Redis)
- A Piston-compatible API for running code
- An OpenAI-compatible API key to use the interview websocket

The problem catalog and workspace APIs can run without an LLM key. Code execution requires the sandbox service; the interview websocket requires the LLM key.

## Run locally on Windows

1. Start PostgreSQL and Redis from the repository root:

   ```powershell
   docker compose -f backend\docker-compose.yml up -d
   ```

2. Configure the backend:

   ```powershell
   Copy-Item backend\.env.example backend\.env
   ```

   Edit `backend\.env` if your database, Redis, Piston, or LLM settings differ. `OPENAI_API_KEY` is only required for the conversational interview.

3. Install and start the backend:

   ```powershell
   Set-Location backend
   py -3.13 -m venv .venv
   .\.venv\Scripts\Activate.ps1
   python -m pip install --upgrade pip
   python -m pip install -e ".[test]"
   python -m uvicorn app.main:app --reload
   ```

   The API is available at `http://localhost:8000`; interactive API documentation is at `http://localhost:8000/docs`. The backend creates its database tables during startup.

4. In a second terminal, install and start the frontend:

   ```powershell
   Set-Location frontend
   npm ci
   npm run dev
   ```

   Open the Vite URL printed in the terminal (normally `http://localhost:5173`). The frontend defaults to `http://localhost:8000/api/v1`; override it by setting `VITE_API_BASE_URL` before starting Vite.

5. Create a demo user and at least one problem through `/docs`:

   - `POST /api/v1/users/demo`
   - `POST /api/v1/problems`

   Provide a language template and test cases in the problem request. The template's driver harness is private and is not returned by the public workspace API.

## Run tests and checks

From the repository root:

```powershell
Set-Location backend
.\.venv\Scripts\Activate.ps1
python -m pytest -q
```

Then, in the frontend directory:

```powershell
Set-Location frontend
npm ci
npm run build
npm run lint
```

The backend tests use an in-memory SQLite database and fake Redis and sandbox clients, so the test suite does not require running external services.

## Stop local services

```powershell
docker compose -f backend\docker-compose.yml down
```

Use `docker compose -f backend\docker-compose.yml down -v` only if you also want to delete the local PostgreSQL data volume.
