# AI SpillGuard — Oil Spill Detection & Segmentation

This repository contains a Streamlit front-end and a FastAPI back-end that together provide
an interface to detect and segment oil spills in satellite images using a pre-trained
Keras/TensorFlow model. The app supports user signup/login, image analysis, result
history, PDF report download, and persistent storage of analyses in PostgreSQL.

Contents
- `frontend/` — Streamlit app (UI, authentication client, image upload, report generation)
- `backend/` — FastAPI server, model utilities and database helpers (SQLAlchemy)
- `final_oil_spill_model.h5` — (optional) pre-trained Keras model (do not commit large models)
- `requirements.txt` — Python dependencies

Quick start (local)
1) Create and activate a virtual environment (PowerShell):
```powershell
python -m venv .venv
.\.venv\Scripts\Activate.ps1
```

2) Install dependencies:
```powershell
pip install -r .\requirements.txt
pip install argon2-cffi reportlab streamlit-lottie streamlit-image-comparison
```

3) Add runtime configuration: create a `.env` file in project root with at least:
```text
DATABASE_URL="postgresql://user:pass@host:port/dbname?sslmode=require"
MODEL_PATH=final_oil_spill_model.h5
SECRET_KEY=your-very-secret-key
```

4) Place the model (optional) or configure remote/model download:
- If you have `final_oil_spill_model.h5`, place it in the project root or update `MODEL_PATH`.
- Recommended: do NOT commit large model files to GitHub. Use cloud storage or Git LFS.

5) Start the backend API (FastAPI + Uvicorn):
```powershell
uvicorn backend.api:app --reload --host 127.0.0.1 --port 8000
```

6) Start the Streamlit frontend:
```powershell
streamlit run .\frontend\app.py
```

User flow / features
- Signup / Login with password hashing (Argon2 via Passlib)
- Upload image (png/jpg) from the Streamlit UI
- Backend runs model inference, generates overlay and percent-of-image spill
- Results are stored in PostgreSQL (analyses table) and shown in "My Past Results"
- Generate and download a PDF report containing original + overlay images and metrics

Notes about the model and large files
- The repo should not track virtual environments, model binaries, or OS/IDE artifacts.
    Use the provided `.gitignore` to exclude `.env`, `venv/`, `*.h5`, `.streamlit/`, etc.
- If you need to include large model files, use Git LFS or host the model on cloud storage and
    provide a small script to download it during setup.

Database
- The app expects a PostgreSQL database; `DATABASE_URL` in `.env` points to the DB.
- The backend runs a table-create routine on startup (`init_db`) so the `users` and
    `analyses` tables are created automatically when the API starts (if permissions allow).

Troubleshooting & tips
- Pre-receive push failure (large files): run the large-file scanner and remove large files
    before pushing. Don't push `venv/` or site-packages.
    Example scanner (PowerShell):
    ```powershell
    Get-ChildItem -Path . -Recurse -File | Where-Object { $_.Length -gt 50MB } |
        Select-Object FullName,@{N='MB';E={[math]::Round($_.Length/1MB,2)}} | Sort-Object MB -Descending
    ```
- Password hashing error (bcrypt 72-byte limit): Argon2 is used in this project via `argon2-cffi`.
- If API import fails, run `python -c "import backend.api; print('ok')"` to display the traceback.

Development & contribution
- Add unit tests under `tests/` (model utilities, API endpoints with test client)
- Add Dockerfiles and a `docker-compose.yml` for local development (API + Streamlit + Postgres)
- Add a CI workflow (GitHub Actions) to run linting and tests on push/PR

References & credits
- The project integrates TensorFlow/Keras for model inference, OpenCV / Pillow for
    image handling, SQLAlchemy for DB ORM, FastAPI for the backend API, and Streamlit for
    the frontend UI.

License
- MIT

If you want, I can now:
- generate a short `setup.sh`/PowerShell script to automate environment setup, or
- add a small `download_model.py` helper that fetches the model from a cloud URL and
    saves it to `MODEL_PATH` (helpful to avoid committing the model). Tell me which.
