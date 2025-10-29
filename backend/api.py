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
import numpy as np
import cv2

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

    # Additional visualizations: predicted mask heatmap, binary mask, and contours overlay
    try:
        # predicted mask heatmap
        pred_resized = cv2.resize(pred_mask, overlay_pil.size, interpolation=cv2.INTER_LINEAR)
        pred_u8 = (np.clip(pred_resized, 0.0, 1.0) * 255.0).astype(np.uint8)
        heat = cv2.applyColorMap(pred_u8, cv2.COLORMAP_JET)
        heat_pil = Image.fromarray(cv2.cvtColor(heat, cv2.COLOR_BGR2RGB))

        # binary mask (already computed in model_utils.generate_overlay as binary_pil)
        binary_bytes = io.BytesIO()
        binary_pil.save(binary_bytes, format="PNG")
        binary_data = binary_bytes.getvalue()

        # contours overlay: draw contours on the resized original
        orig_resized = overlay_pil.convert("RGB")
        orig_np = np.array(orig_resized)
        # binary array for contours
        bin_np = np.array(binary_pil)
        # ensure single channel binary
        if bin_np.ndim == 3:
            bin_np = cv2.cvtColor(bin_np, cv2.COLOR_BGR2GRAY)
        contours, _ = cv2.findContours((bin_np > 0).astype(np.uint8), cv2.RETR_EXTERNAL, cv2.CHAIN_APPROX_SIMPLE)
        cont_img = orig_np.copy()
        cv2.drawContours(cont_img, contours, -1, (0, 255, 0), 2)
        contours_pil = Image.fromarray(cont_img)

        # convert heatmap and contours to bytes
        heat_bytes = io.BytesIO()
        heat_pil.save(heat_bytes, format="PNG")
        heat_data = heat_bytes.getvalue()

        contours_bytes = io.BytesIO()
        contours_pil.save(contours_bytes, format="PNG")
        contours_data = contours_bytes.getvalue()
    except Exception as e:
        # If any visualization fails, don't block the main result — log and continue without extras
        print(f"[DEBUG] Extra visuals generation failed: {e}")
        heat_data = None
        binary_data = None
        contours_data = None

    # Save analysis to DB
    try:
        analysis_id = db.save_analysis(user_id=current_user["user_id"], spill_percentage=spill_pct, original_bytes=contents, overlay_bytes=overlay_data, filename=file.filename)
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"DB save error: {e}")

    return {
        "analysis_id": analysis_id,
        "spill_percentage": spill_pct,
        "overlay_image": base64.b64encode(overlay_data).decode("utf-8"),
        "predicted_mask": base64.b64encode(heat_data).decode("utf-8") if heat_data else None,
        "binary_mask": base64.b64encode(binary_data).decode("utf-8") if binary_data else None,
        "contours_overlay": base64.b64encode(contours_data).decode("utf-8") if contours_data else None,
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
