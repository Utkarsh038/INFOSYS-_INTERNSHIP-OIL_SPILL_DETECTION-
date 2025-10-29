import io
from pathlib import Path
import numpy as np
from PIL import Image
import cv2
import tensorflow as tf
from functools import lru_cache
import os


@lru_cache(maxsize=1)
def load_model(model_path: str):
    """Load and return a Keras model. Cached with lru_cache so it's only loaded once.

    Raises RuntimeError if model not found.
    """
    model_file = Path(model_path)
    if not model_file.exists():
        # Try to find from env if not provided
        alt = os.getenv("MODEL_PATH")
        if alt and Path(alt).exists():
            model_file = Path(alt)
        else:
            raise RuntimeError(f"Model file not found at {model_path}. Place the .h5 file there or set MODEL_PATH in .env")
    model = tf.keras.models.load_model(str(model_file), compile=False)
    return model


def preprocess_image(pil_image: Image.Image, target_size=(256, 256)) -> np.ndarray:
    """Convert PIL image to model-ready numpy array.

    Steps: RGB, resize, normalize to [0,1], add batch dim.
    """
    img = pil_image.convert("RGB")
    img = img.resize(target_size)
    arr = np.asarray(img).astype(np.float32) / 255.0
    arr = np.expand_dims(arr, axis=0)
    return arr


def predict_mask(model, preprocessed: np.ndarray) -> np.ndarray:
    """Run model.predict and return single-mask (H,W) with values in [0,1]."""
    if model is None:
        raise RuntimeError("Model not loaded")
    pred = model.predict(preprocessed)
    # Expecting output shape (1, H, W, 1) or (1, H, W)
    pred = np.asarray(pred)
    if pred.ndim == 4:
        pred = pred[0, ..., 0]
    elif pred.ndim == 3:
        pred = pred[0, ...]
    else:
        raise ValueError(f"Unexpected prediction shape: {pred.shape}")
    # Ensure float32
    return pred.astype(np.float32)


def generate_overlay(original_pil: Image.Image, mask: np.ndarray, threshold: float = 0.5, opacity: float = 0.4, out_size=(256, 256)) -> tuple:
    """Create overlay image by thresholding mask and blending red mask over original.

    Returns: (overlay_pil, binary_mask_pil, spill_percentage_float)
    """
    # Resize original to out_size for a pixel-for-pixel overlay
    orig_resized = original_pil.convert("RGB").resize(out_size)
    h, w = out_size[1], out_size[0]

    # Ensure mask is the same size
    mask_resized = cv2.resize(mask, out_size, interpolation=cv2.INTER_LINEAR)
    binary = (mask_resized >= threshold).astype(np.uint8) * 255

    # Create red mask (RGB)
    red_mask = np.zeros((out_size[1], out_size[0], 3), dtype=np.uint8)
    red_mask[..., 0] = binary  # R channel

    orig_np = np.asarray(orig_resized).astype(np.uint8)

    # Blend
    blended = cv2.addWeighted(orig_np, 1.0, red_mask, float(opacity), 0)

    overlay_pil = Image.fromarray(blended)
    binary_pil = Image.fromarray(binary)

    # Compute spill percentage
    spill_pct = float(np.count_nonzero(binary) / (binary.size) * 100.0)

    return overlay_pil, binary_pil, spill_pct


def pil_image_to_bytes(pil_img: Image.Image, fmt="PNG") -> bytes:
    buf = io.BytesIO()
    pil_img.save(buf, format=fmt)
    return buf.getvalue()
