import streamlit as st
from PIL import Image
import io
import os
import requests
import base64
from streamlit_lottie import st_lottie
from streamlit_image_comparison import image_comparison
from reportlab.lib.pagesizes import letter
from reportlab.pdfgen import canvas
from reportlab.lib.utils import ImageReader

# Frontend will call API backend
API_URL = os.getenv("API_URL", "http://127.0.0.1:8000")


def safe_rerun():
    """Try to rerun the Streamlit app in a way that works across versions.

    - Prefer st.experimental_rerun() when available.
    - Otherwise update query params (which triggers a rerun), or toggle a session flag.
    """
    try:
        if hasattr(st, "experimental_rerun"):
            st.experimental_rerun()
            return
    except Exception:
        pass

    try:
        # updating query params triggers a rerun in most Streamlit versions
        import uuid

        key = {"_rerun": uuid.uuid4().hex}
        # prefer the public API where available
        if hasattr(st, "set_query_params"):
            try:
                st.set_query_params(**key)
                return
            except Exception:
                pass
        # older or alternate names
        if hasattr(st, "experimental_set_query_params"):
            try:
                st.experimental_set_query_params(**key)
                return
            except Exception:
                pass
        # some versions support assigning to st.query_params directly
        try:
            st.query_params = key
            return
        except Exception:
            pass
    except Exception:
        pass

    # Fallback: toggle a dummy session_state key and stop execution
    st.session_state["_rerun_toggle"] = not st.session_state.get("_rerun_toggle", False)
    try:
        st.stop()
    except Exception:
        # If st.stop isn't available, just return
        return


# --- Styling / helpers -------------------------------------------------
CSS = """
<style>
.card { background: rgba(255,255,255,0.02); border-radius: 12px; padding: 18px; box-shadow: 0 6px 24px rgba(0,0,0,0.6); margin-bottom: 16px; }
.hero { display:flex; align-items:center; gap:16px; }
.hero-logo{ width:64px; height:64px; border-radius:12px; background: linear-gradient(135deg,#06b6d4,#ef4444); display:flex; align-items:center; justify-content:center; font-weight:700; color:white;}
.hero-title{ font-size:34px; font-weight:700; margin:0; }
.hero-sub{ color:#9ca3af; margin-top:4px }
</style>
"""


def insert_css_and_hero():
    st.markdown(CSS, unsafe_allow_html=True)
    # small hero area
    st.markdown('<div class="card"><div class="hero"><div class="hero-logo">🌊</div><div><div class="hero-title">Oil Spill Detection & Segmentation</div><div class="hero-sub">Upload satellite images and detect oil spills with a single click</div></div></div></div>', unsafe_allow_html=True)


def load_lottie_url(url: str):
    try:
        r = requests.get(url)
        if r.status_code == 200:
            return r.json()
    except Exception:
        return None


def ensure_api_reachable():
    try:
        requests.get(f"{API_URL}/docs", timeout=2)
    except Exception:
        # Not fatal here; we'll show errors when calling endpoints
        pass


def signup_flow():
    st.header("Sign Up")
    username = st.text_input("Choose a Username", key="su_user")
    password = st.text_input("Choose a Password", type="password", key="su_pass")
    if st.button("Sign Up"):
        if not username or not password:
            st.warning("Provide username and password")
            return
        try:
            resp = requests.post(f"{API_URL}/signup", data={"username": username, "password": password}, timeout=10)
            if resp.status_code == 200:
                st.success("Sign up successful — you can now login")
            else:
                st.error(f"Sign up failed: {resp.text}")
        except Exception as e:
            st.error(f"Sign up error: {e}")


def login_flow():
    st.header("Login")
    username = st.text_input("Username", key="li_user")
    password = st.text_input("Password", type="password", key="li_pass")
    if st.button("Login"):
        try:
            resp = requests.post(f"{API_URL}/login", data={"username": username, "password": password}, timeout=10)
            if resp.status_code == 200:
                token = resp.json().get("access_token")
                st.session_state["logged_in"] = True
                st.session_state["token"] = token
                st.session_state["username"] = username
                # Trigger a safe rerun so main() will redraw the logged-in UI
                safe_rerun()
            else:
                st.error(f"Login failed: {resp.text}")
        except Exception as e:
            st.error(f"Login error: {e}")


def logout():
    for k in ["logged_in", "token", "username"]:
        if k in st.session_state:
            del st.session_state[k]
    safe_rerun()


def image_analyzer_page():
    # Insert hero and CSS for a polished look
    insert_css_and_hero()
    st.header("Image Analyzer")
    uploaded = st.file_uploader("Choose an image...", type=["jpg", "jpeg", "png"]) 
    threshold = st.sidebar.slider("Confidence Threshold", 0.0, 1.0, 0.5)
    opacity = st.sidebar.slider("Overlay Opacity", 0.0, 1.0, 0.4)

    col1, col2 = st.columns(2)
    if uploaded is not None:
        image = Image.open(uploaded)
        col1.header("Original Image")
        col1.image(image, use_column_width=True)

        # show an animated loader (decorative) while analysis runs
        lottie_busy = load_lottie_url("https://assets7.lottiefiles.com/packages/lf20_j1adxtyb.json")
        if lottie_busy:
            st_lottie(lottie_busy, height=120, key="loading")

        with st.spinner("Analyzing image via API..."):
            try:
                headers = {}
                token = st.session_state.get("token")
                if token:
                    headers["Authorization"] = f"Bearer {token}"
                files = {"file": (uploaded.name, uploaded.getvalue(), uploaded.type)}
                data = {"threshold": str(threshold), "opacity": str(opacity)}
                resp = requests.post(f"{API_URL}/analyze", files=files, data=data, headers=headers, timeout=60)
                if resp.status_code != 200:
                    st.error(f"Analyze error: {resp.text}")
                    return
                j = resp.json()
                spill_pct = j.get("spill_percentage", 0.0)
                overlay_b64 = j.get("overlay_image")
                overlay_bytes = base64.b64decode(overlay_b64)
                overlay_pil = Image.open(io.BytesIO(overlay_bytes))
            except Exception as e:
                st.error(f"Analyze request failed: {e}")
                return

        col2.header("Prediction Overlay")
        # interactive comparison slider (left original, right overlay)
        try:
            image_comparison(img1=image, img2=overlay_pil, label1="Original", label2="Overlay", width=650)
        except Exception:
            # fallback to static image
            col2.image(overlay_pil, use_column_width=True)

        st.subheader("Analysis Results")
        st.metric("Spill Coverage", f"{spill_pct:.2f}%")
        if spill_pct > 0:
            st.success("Spill detected")
        else:
            st.info("No spill detected")

        # Download overlay
        st.download_button("Download overlay", data=io.BytesIO(overlay_bytes), file_name="overlay.png", mime="image/png")
    else:
        st.info("Upload an image to analyze")


def past_results_page():
    st.header("My Past Results")
    token = st.session_state.get("token")
    if not token:
        st.error("Log in to view past results")
        return
    headers = {"Authorization": f"Bearer {token}"}
    try:
        resp = requests.get(f"{API_URL}/analyses", headers=headers, timeout=10)
        if resp.status_code != 200:
            st.error(f"Failed to fetch analyses: {resp.text}")
            return
        rows = resp.json()
    except Exception as e:
        st.error(f"Error fetching analyses: {e}")
        return

    if not rows:
        st.info("No past results")
        return

    # show as a responsive grid of cards (3 columns)
    cols = st.columns(3)
    for i, r in enumerate(rows):
        ts = r.get("timestamp")
        pct = r.get("spill_percentage", 0.0)
        orig_b = base64.b64decode(r.get("original_image"))
        over_b = base64.b64decode(r.get("overlay_image"))
        col = cols[i % 3]
        with col:
            st.markdown("<div class='card'>", unsafe_allow_html=True)
            st.markdown(f"**{ts}**")
            st.image(Image.open(io.BytesIO(orig_b)), use_column_width=True)
            st.markdown(f"**Spill:** {pct:.2f}%")
            c1, c2, c3 = st.columns([1,1,1])
            # View (expander) button
            if c1.button("View", key=f"view_{r['analysis_id']}"):
                with st.expander("Details"):
                    col1, col2 = st.columns(2)
                    col1.image(Image.open(io.BytesIO(orig_b)))
                    col2.image(Image.open(io.BytesIO(over_b)))
            # Download overlay
            if c2.download_button("Download", data=io.BytesIO(over_b), file_name=f"overlay_{r['analysis_id']}.png", mime="image/png", key=f"dl_{r['analysis_id']}"):
                pass
            # Delete
            if c3.button("Delete", key=f"del_{r['analysis_id']}"):
                try:
                    headers = {"Authorization": f"Bearer {token}"}
                    resp = requests.delete(f"{API_URL}/analyses/{r['analysis_id']}", headers=headers, timeout=10)
                    if resp.status_code == 200:
                        st.success("Deleted")
                        safe_rerun()
                    else:
                        st.error(f"Delete failed: {resp.text}")
                except Exception as e:
                    st.error(f"Delete error: {e}")

            st.markdown("</div>", unsafe_allow_html=True)


def create_pdf_report(original_bytes: bytes, overlay_bytes: bytes, spill_pct: float) -> bytes:
    buf = io.BytesIO()
    c = canvas.Canvas(buf, pagesize=letter)
    width, height = letter

    # Title
    c.setFont("Helvetica-Bold", 18)
    c.drawString(40, height - 40, "Oil Spill Analysis Report")
    c.setFont("Helvetica", 12)
    c.drawString(40, height - 60, f"Spill Coverage: {spill_pct:.2f}%")
    c.drawString(40, height - 80, f"Generated: ")

    # Images
    try:
        orig_img = ImageReader(io.BytesIO(original_bytes))
        over_img = ImageReader(io.BytesIO(overlay_bytes))
        img_w = 260
        img_h = 260
        c.drawImage(orig_img, 40, height - 120 - img_h, width=img_w, height=img_h)
        c.drawImage(over_img, 320, height - 120 - img_h, width=img_w, height=img_h)
    except Exception:
        # If images fail to embed, ignore
        pass

    c.showPage()
    c.save()
    buf.seek(0)
    return buf.getvalue()


def main():
    st.set_page_config(page_title="Oil Spill Detection & Segmentation", layout="wide")
    ensure_api_reachable()

    if "logged_in" not in st.session_state:
        st.session_state["logged_in"] = False

    if not st.session_state.get("logged_in"):
        st.title("🌊 Oil Spill Detection & Segmentation")
        tabs = st.tabs(["Login", "Sign Up"])
        with tabs[0]:
            login_flow()
        with tabs[1]:
            signup_flow()
        return

    # Logged in: show sidebar and pages
    st.sidebar.write(f"Welcome, {st.session_state.get('username')}!")
    page = st.sidebar.radio("Navigation", ["Image Analyzer", "My Past Results"]) 
    if st.sidebar.button("Logout"):
        logout()

    if page == "Image Analyzer":
        image_analyzer_page()
    elif page == "My Past Results":
        past_results_page()


if __name__ == "__main__":
    main()
