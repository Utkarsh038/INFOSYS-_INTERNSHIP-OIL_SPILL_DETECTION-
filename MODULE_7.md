# — Operational Documentation, Testing & Deployment

This document gathers the required deliverables: installation and runtime instructions, API and DB contracts, testing guidance, CI/CD and Docker instructions, deployment checklist, security and monitoring notes, and acceptance criteria. Use this as the canonical operational / handover doc for the project.

## 1. Purpose & Scope
- Purpose: Provide a single, ready-to-use operations guide so a developer or operator can run, test, and deploy the Oil Spill Detection application.
- Scope: local development, CI/testing, containerized deployment, runtime configuration, model handling, database migrations and backups, logging, monitoring and security hardening.

## 2. Deliverables for 
- `MODULE_7.md` (this document)
- `setup.ps1` / `setup.sh` (automation script — optional)
- `Dockerfile` for the backend and `Dockerfile` or instructions for the Streamlit frontend
- `docker-compose.yml` for local multi-service dev (backend + frontend + postgres)
- `tests/` folder with unit and integration tests (pytest)
- GitHub Actions workflow: `/.github/workflows/ci.yml` running lint/test
- Deployment instructions for Render, Streamlit Cloud, or a container host

## 3. Architecture Overview
- Frontend: Streamlit app (`frontend/app.py`) — user login/signup, image upload, history, PDF generation
- Backend: FastAPI (`backend/api.py`) — endpoints for auth, analysis, listing and deletion
- Model utils: `backend/model_utils.py` — load model, preprocess, predict, overlay generation
- Database: PostgreSQL (Neon or hosted Postgres) via SQLAlchemy models in `backend/db.py`

Diagram (text):
User -> Streamlit UI -> FastAPI -> (Model utils + DB) -> PostgreSQL

## 4. Environment & Secrets
- Required environment variables (put in `.env` or secret manager):
  - DATABASE_URL — full Postgres connection string (do not commit)
  - MODEL_PATH — relative path or cloud URL to model file
  - SECRET_KEY — JWT secret for auth
  - OPTIONAL: MODEL_DOWNLOAD_URL — if using a hosted model

- `.gitignore` must include: `.env`, `venv/`, `*.h5`, `.streamlit/`, `__pycache__/`, `.ipynb_checkpoints`

## 5. API Contract (Endpoints)
All endpoints accept/return JSON unless otherwise stated. Authentication uses Bearer JWT.

- POST /signup
  - Input: JSON { "username": "...", "password": "..." }
  - Output: 201 created or 400 error

- POST /login
  - Input: JSON { "username": "...", "password": "..." }
  - Output: { "access_token": "<jwt>", "token_type": "bearer" }

- POST /analyze
  - Auth: Bearer
  - Input: multipart/form-data: file (image)
  - Output: JSON { "analysis_id": int, "spill_pct": float, "overlay_b64": "...", "original_b64": "..." }

- GET /analyses
  - Auth: Bearer
  - Output: list of analyses with metadata and base64 images

- DELETE /analyses/{id}
  - Auth: Bearer
  - Output: 204 on success

Implementation notes
- Large binary data should not be embedded into JSON for production; prefer S3 or object store + a URL.

## 6. Database Schema (short)
- users: id (PK), username (unique), password_hash, created_at
- analyses: id (PK), user_id (FK -> users.id), timestamp, spill_pct (numeric), original_image (bytea or external URL), overlay_image (bytea or external URL)

Use SQLAlchemy models in `backend/db.py`. For production migrations use Alembic.

## 7. Local Development — Steps
1. Create venv and activate
   - PowerShell:
     ```powershell
     python -m venv .venv
     .\.venv\Scripts\Activate.ps1
     ```
2. Install dependencies
   ```powershell
   pip install -r requirements.txt
   pip install argon2-cffi reportlab streamlit-lottie streamlit-image-comparison
   ```
3. Create `.env` with required variables (see Environment & Secrets)
4. Start backend
   ```powershell
   uvicorn backend.api:app --reload --host 127.0.0.1 --port 8000
   ```
5. Start frontend
   ```powershell
   streamlit run .\frontend\app.py
   ```

## 8. Model handling
- Never commit `final_oil_spill_model.h5` to git. Options:
  - Host in cloud storage (S3/Spaces/GCS) and add `MODEL_DOWNLOAD_URL` to `.env` + a helper script `download_model.py` that fetches it during setup.
  - Use Git LFS (configure `git lfs track "*.h5"`) if you must keep the file in the repository and are comfortable with LFS.

## 9. Testing guidance
- Unit tests (pytest) to add:
  - `tests/test_model_utils.py` — preprocess_image, predict_mask (use a tiny dummy model or mock the model)
  - `tests/test_db.py` — create user, save analysis, get analyses using a temporary SQLite in-memory URL or test Postgres container
  - `tests/test_api.py` — FastAPI TestClient tests for signup/login/analyze (mock file upload and mock model to avoid heavy inference)

Example pytest test skeleton (short):
```python
def test_preprocess_image(tmp_path):
    # prepare a small sample image and call preprocess_image
    pass
```

CI
- Add `.github/workflows/ci.yml` that:
  - Checks out code
  - Sets up Python
  - Installs dependencies
  - Runs pytest
  - Optionally runs a lint step (flake8/black)

## 10. Docker and docker-compose (recommended)
- Backend Dockerfile (example summary):
  - base: python:3.11-slim
  - install dependencies, copy `backend/` code, `requirements.txt`, expose port 8000, run `uvicorn backend.api:app --host 0.0.0.0 --port 8000`
- Frontend: run Streamlit in a container or deploy Streamlit Cloud.
- `docker-compose.yml` should include services: `db` (postgres), `api`, `frontend` (optional), and a volume for DB persistence.

## 11. Deployment checklist
- Prepare secrets in the target platform (Render/Heroku/Streamlit Cloud): `DATABASE_URL`, `SECRET_KEY`, `MODEL_DOWNLOAD_URL` (if applicable).
- Ensure your model is accessible to the backend container via download or mounted volume.
- Set allowed hosts / CORS if exposing API publicly.
- Use HTTPS for all production services.

## 12. Monitoring & Logging
- Backend: ensure requests, errors and inference durations are logged. Use structured logs (JSON) if integrating with a log collector.
- Add basic metrics: request count, error count, avg inference time. Export to Prometheus or a platform metric collector.
- Optionally add health and readiness endpoints to the FastAPI app (`/healthz`).

## 13. Security checklist
- Do not commit `.env` or secret material.
- Use Argon2 (already configured) for password hashing.
- Use HTTPS and rotate `SECRET_KEY` for JWTs as needed.
- Limit model-hosting URLs and secure access to object storage (signed URLs).
- Add rate limiting on public endpoints (e.g., analyze) to mitigate abuse.

## 14. Backup & Rollback
- Regularly back up the Postgres DB (managed provider snapshot or pg_dump).
- Tag container images and use immutable tags in deployments.
- Have a tested rollback plan (deploy previous image tag and restore DB backup if necessary).

## 15. Acceptance criteria ()
The module is complete when:
- A maintainer can run the app locally following the steps above.
- CI runs tests and passes on push/PRs.
- A Docker-based deployment is configured and can be launched locally via `docker-compose up`.
- The app runs on a cloud target with secrets configured and without committing sensitive files.
- Basic monitoring and logging are in place and documented.

## 16. Appendix — Useful commands
- Large-file scanner (PowerShell):
```powershell
Get-ChildItem -Path . -Recurse -File | Where-Object { $_.Length -gt 50MB } |
  Select-Object FullName,@{N='MB';E={[math]::Round($_.Length/1MB,2)}} | Sort-Object MB -Descending
```
- Remove file from git index (keep local copy):
```powershell
git rm --cached path\to\file
git commit -m "Remove large file from index"
```

---

If you'd like, I can now:
- create `download_model.py` and `setup.ps1` to automate model download and environment setup, or
- scaffold `tests/` with the pytest skeletons mentioned above, or
- add a `docker-compose.yml` and Dockerfile templates. Tell me which and I'll implement it next.
