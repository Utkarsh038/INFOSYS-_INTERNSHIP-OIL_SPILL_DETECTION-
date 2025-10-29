# Oil Spill Detection & Segmentation

A Streamlit app + FastAPI backend to detect and segment oil spills using a pre-trained Keras model.

Quick start
1. Create and activate a virtual environment (recommended):
```powershell
python -m venv .venv
.\.venv\Scripts\Activate.ps1
```

2. Install dependencies:
```powershell
python -m pip install -r .\requirements.txt
python -m pip install argon2-cffi reportlab streamlit-lottie streamlit-image-comparison
```

3. Create a `.env` file in the project root with these variables (example):
```
DATABASE_URL="postgresql://neondb_owner:...@ep-.../neondb?sslmode=require&channel_binding=require"
MODEL_PATH=final_oil_spill_model.h5
SECRET_KEY=your-secret-key-here
```

4. Place your Keras model `final_oil_spill_model.h5` in the project root (or update `MODEL_PATH`).

5. Start the backend API (FastAPI / Uvicorn):
```powershell
uvicorn backend.api:app --reload --host 127.0.0.1 --port 8000
```

6. Start the Streamlit frontend:
```powershell
streamlit run .\frontend\app.py
```

Development notes
- The app stores users and analysis records in the database referenced by `DATABASE_URL`. For quick local development you can run a local Postgres or adjust `DATABASE_URL`.
- The frontend calls the API endpoints for signup/login/analyze/listing/deletion.
- PDF report generation is implemented client-side in the Streamlit app (ReportLab).

Troubleshooting
- If the API fails to start, run `python -c "import backend.api; print('ok')"` to surface import errors.
- If you see bcrypt-related password errors, ensure `argon2-cffi` is installed (the project uses Argon2 via Passlib).

Next improvements
- Add unit tests and CI, Docker compose for local dev, background processing for batch uploads, and enhanced history management.

License: MIT
