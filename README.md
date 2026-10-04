# AI Document Assistant

Next.js frontend and FastAPI backend for summarizing and asking questions about PDF documents.

## Run locally

Start the API from `backend`:

```powershell
cd backend
python -m pip install -r requirements.txt
python -m uvicorn app.main:app --reload --port 8000
```

Set `OPENROUTER_API_KEY` and `JWT_SECRET` in `backend/.env`. The frontend reads
`NEXT_PUBLIC_API_URL` from `.env.local` in the repository root; set it to
`http://localhost:8000`.

In another terminal, start the frontend:

```powershell
npm install
npm run dev
```

## Deploy for free

The frontend is hosted on Vercel and the API on Render. Both services use this
GitHub repository. Free-tier limits and availability may change.

### 1. Push the repository to GitHub

Create a GitHub repository and push this project. Do not commit `.env`,
`.env.local`, or `backend/app.db`; these are ignored by Git.

### 2. Deploy the API on Render

In Render, create a **Blueprint** and connect the GitHub repository containing
`render.yaml`. The blueprint creates the Python web service with `backend` as
its root directory.

In the Render service environment, set `OPENROUTER_API_KEY` to your
OpenRouter key. Optionally set `ADMIN_EMAILS` to comma-separated admin email
addresses. Render generates `JWT_SECRET` for the service.

After deployment, copy the service URL, for example
`https://ai-document-assistant-api.onrender.com`.

### 3. Deploy the frontend on Vercel

Import the same GitHub repository into Vercel. Keep the project root at the
repository root so Vercel detects the Next.js app.

Add the environment variable `NEXT_PUBLIC_API_URL` with the Render service URL
(no trailing slash), then deploy.

### 4. Allow the frontend site to call the API

The Render blueprint includes the production frontend origin and localhost in
`CORS_ORIGINS`. If the frontend is deployed to a different domain, update the
variable in Render to include its exact origin. For multiple trusted origins,
use comma-separated URLs. Do not include paths or trailing slashes.

If you change `NEXT_PUBLIC_API_URL` in Vercel, redeploy the frontend because
Next.js embeds this public variable during the build.

## Free-tier notes

- Render free web services may sleep when idle, so the first API request after
  inactivity can be slow.
- The backend currently uses a local SQLite database. Render's free service
  does not provide persistent local storage, so accounts and documents can be
  lost after a restart or redeploy. Use an external database before relying on
  production data.
