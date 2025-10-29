import os
import io
import base64
from datetime import datetime, timedelta
from typing import Optional

from fastapi import FastAPI, HTTPException, Depends, UploadFile, File, Form
from fastapi.security import OAuth2PasswordBearer
from pydantic import BaseModel
from jose import JWTError, jwt
from dotenv import load_dotenv
from PIL import Image

import backend.model_utils as model_utils
import backend.db as db

load_dotenv()

SECRET_KEY = os.getenv("SECRET_KEY", "change-this-secret")
ALGORITHM = "HS256"
ACCESS_TOKEN_EXPIRE_DAYS = 7

app = FastAPI(title="Oil Spill Detection API")
oauth2_scheme = OAuth2PasswordBearer(tokenUrl="/login")


@app.on_event("startup")
def startup_event():
    # Attempt to create DB tables on startup. If DB is unreachable, log the error
    try:
        db.init_db()
        print("Database initialized (tables created if they did not exist)")
    except Exception as e:
        # Raise or log? We log the error and continue so the API can start and show errors on DB ops
        print(f"Warning: failed to initialize database tables: {e}")


class Token(BaseModel):
    access_token: str
    token_type: str


def create_access_token(data: dict, expires_delta: Optional[timedelta] = None):
    to_encode = data.copy()
    if expires_delta:
        expire = datetime.utcnow() + expires_delta
    else:
        expire = datetime.utcnow() + timedelta(days=ACCESS_TOKEN_EXPIRE_DAYS)
    to_encode.update({"exp": expire})
    encoded_jwt = jwt.encode(to_encode, SECRET_KEY, algorithm=ALGORITHM)
    return encoded_jwt


def get_current_user(token: str = Depends(oauth2_scheme)):
    credentials_exception = HTTPException(status_code=401, detail="Could not validate credentials")
    try:
        payload = jwt.decode(token, SECRET_KEY, algorithms=[ALGORITHM])
        user_id: int = int(payload.get("sub"))
        username: str = payload.get("username")
        if user_id is None or username is None:
            raise credentials_exception
        return {"user_id": user_id, "username": username}
    except JWTError:
        raise credentials_exception


@app.post("/signup")
def signup(username: str = Form(...), password: str = Form(...)):
    uid = db.create_user(username, password)
    if uid is None:
        raise HTTPException(status_code=400, detail="Username already taken")
    return {"user_id": uid}


@app.post("/login", response_model=Token)
def login(username: str = Form(...), password: str = Form(...)):
    uid = db.verify_user(username, password)
    if uid is None:
        raise HTTPException(status_code=401, detail="Invalid credentials")
    access_token = create_access_token(data={"sub": str(uid), "username": username})
    return {"access_token": access_token, "token_type": "bearer"}


@app.post("/analyze")
def analyze(file: UploadFile = File(...), threshold: float = Form(0.5), opacity: float = Form(0.4), current_user: dict = Depends(get_current_user)):
    # Ensure model is loaded
    model_path = os.getenv("MODEL_PATH", "final_oil_spill_model.h5")
    try:
        model = model_utils.load_model(model_path)
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Model load error: {e}")

    contents = file.file.read()
    try:
        pil = Image.open(io.BytesIO(contents))
    except Exception as e:
        raise HTTPException(status_code=400, detail=f"Invalid image: {e}")

    pre = model_utils.preprocess_image(pil)
    pred_mask = model_utils.predict_mask(model, pre)
    overlay_pil, binary_pil, spill_pct = model_utils.generate_overlay(pil, pred_mask, threshold=threshold, opacity=opacity)

    overlay_bytes = io.BytesIO()
    overlay_pil.save(overlay_bytes, format="PNG")
    overlay_data = overlay_bytes.getvalue()

    # Save analysis to DB
    try:
        analysis_id = db.save_analysis(user_id=current_user["user_id"], spill_percentage=spill_pct, original_bytes=contents, overlay_bytes=overlay_data, filename=file.filename)
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"DB save error: {e}")

    return {
        "analysis_id": analysis_id,
        "spill_percentage": spill_pct,
        "overlay_image": base64.b64encode(overlay_data).decode("utf-8"),
        "original_filename": file.filename,
    }


@app.get("/analyses")
def list_analyses(current_user: dict = Depends(get_current_user)):
    rows = db.get_analyses_for_user(current_user["user_id"])
    out = []
    for r in rows:
        out.append({
            "analysis_id": r["analysis_id"],
            "timestamp": r["timestamp"].isoformat(),
            "spill_percentage": r["spill_percentage"],
            "original_filename": r.get("original_filename"),
            "overlay_image": base64.b64encode(r["overlay_image_blob"]).decode("utf-8"),
            "original_image": base64.b64encode(r["original_image_blob"]).decode("utf-8"),
        })
    return out


@app.delete("/analyses/{analysis_id}")
def delete_analysis(analysis_id: int, current_user: dict = Depends(get_current_user)):
    # Ensure the analysis belongs to the current user before deleting
    rows = db.get_analyses_for_user(current_user["user_id"])
    found = False
    for r in rows:
        if r["analysis_id"] == analysis_id:
            found = True
            break
    if not found:
        raise HTTPException(status_code=404, detail="Analysis not found")
    ok = db.delete_analysis(analysis_id)
    if not ok:
        raise HTTPException(status_code=500, detail="Failed to delete")
    return {"deleted": analysis_id}
