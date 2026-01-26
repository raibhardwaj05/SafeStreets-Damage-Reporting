# ============================
# RoadGuard — Streamlit App
# Dark Theme with Home Cards & Navigation
# ============================

import os
import tempfile
from pathlib import Path
import numpy as np
import imageio
import streamlit as st
from PIL import Image
import plotly.graph_objects as go
from ultralytics import YOLO

# Environment variables
os.environ["YOLO_HEADLESS"] = "True"
os.environ["OPENCV_VIDEOIO_PRIORITY_MSMF"] = "0"

# Page config
st.set_page_config(
    page_title="RoadGuard - Road Damage Detection System",
    page_icon="🛣️",
    layout="wide",
    initial_sidebar_state="expanded",
)

# ===============================
# DARK THEME STYLES
# ===============================
st.markdown("""
    <style>
        .stApp {
            background-color: #121212;
            color: #e0e0e0;
            font-family: 'Segoe UI', sans-serif;
        }
        h1, h2 {
            color: #80cbc4;
            text-align: center;
        }
        [data-testid="stSidebar"] {
            background-color: #1e1e1e;
            color: #e0e0e0;
        }
        .stButton>button {
            background-color: #ff9800;
            color: #000;
            border-radius: 8px;
            padding: 0.6em 1.2em;
            font-weight: bold;
            border: none;
        }
        .stButton>button:hover {
            background-color: #f57c00;
            color: #fff;
        }
        .card {
            background-color: #1e1e1e;
            border-radius: 12px;
            padding: 1.5rem;
            margin: 1rem;
            box-shadow: 0 4px 10px rgba(0,0,0,0.6);
            transition: transform 0.2s;
        }
        .card:hover {
            transform: translateY(-5px);
        }
        .card h3 {
            color: #ffb74d;
            margin-bottom: 0.5rem;
        }
        .card p {
            color: #f5f5f5;
            font-size: 0.95rem;
            line-height: 1.4;
        }
        ul li {
            color: #f5f5f5;
        }
    </style>
""", unsafe_allow_html=True)

# Cleanup old temp files
for f in st.session_state.get("temp_files", []):
    try:
        os.unlink(f)
    except:
        pass
st.session_state["temp_files"] = []

MODEL_DIR = Path(__file__).parent / "model"

def get_model_path():
    pt_files = list(MODEL_DIR.glob("*.pt"))
    return str(pt_files[0]) if pt_files else None

@st.cache_resource
def load_model():
    model_path = get_model_path()
    if not model_path:
        raise FileNotFoundError("Model file not found in /model")
    return YOLO(model_path)

# ===============================
# IMAGE DETECTION
# ===============================
def run_image_detection(image_array, model):
    results = model(image_array, conf=0.1, iou=0.5, verbose=False)
    annotated_pil = results[0].plot(pil=True)
    annotated_rgb = np.array(annotated_pil)
    return annotated_rgb, results[0]

# ===============================
# VIDEO DETECTION
# ===============================
def run_video_detection(video_path, model, progress_bar=None, status=None):
    reader = imageio.get_reader(video_path)
    fps = reader.get_meta_data().get("fps", 24)
    frames = []
    total_frames = reader.count_frames() if hasattr(reader, "count_frames") else None
    frame_idx = 0

    with tempfile.NamedTemporaryFile(suffix=".mp4", delete=False) as tmp:
        output_path = tmp.name

    for frame in reader:
        frame_rgb = frame
        frame_bgr = frame_rgb[..., ::-1]
        results = model(frame_bgr, conf=0.1, iou=0.5, verbose=False)
        annotated_pil = results[0].plot(pil=True)
        annotated_rgb = np.array(annotated_pil)
        combined = np.hstack((frame_rgb, annotated_rgb))
        frames.append(combined)

        frame_idx += 1
        if progress_bar and total_frames:
            progress = frame_idx / total_frames
            progress_bar.progress(progress, text=f"Processing {frame_idx}/{total_frames}")

    reader.close()
    writer = imageio.get_writer(output_path, fps=fps, codec="libx264", macro_block_size=None)
    for f in frames:
        writer.append_data(f)
    writer.close()
    return output_path

# ===============================
# PIE CHART
# ===============================
def create_damage_ratio_chart(reported, maintained):
    labels = ['Maintained', 'Pending']
    values = [maintained, reported - maintained]
    colors = ['#4caf50', '#ff5722']
    fig = go.Figure(data=[go.Pie(
        labels=labels,
        values=values,
        hole=0.4,
        marker_colors=colors,
        textinfo='label+percent',
        textfont_size=16,
        marker=dict(line=dict(color='#121212', width=3))
    )])
    fig.update_layout(
        title={'text': 'Road Damage Status', 'x': 0.5, 'font': {'color': '#e0e0e0'}},
        showlegend=True,
        height=400,
        paper_bgcolor='#121212',
        plot_bgcolor='#121212',
        font=dict(color='#e0e0e0')
    )
    return fig

# ===============================
# HOME PAGE
# ===============================
def home_page():
    st.markdown("<h1>🛣️ RoadGuard Dashboard</h1>", unsafe_allow_html=True)

    # Cards explaining project
    col1, col2 = st.columns(2)
    with col1:
        st.markdown("""
        <div class="card">
            <h3>🚧 What is RoadGuard?</h3>
            <p>RoadGuard is an AI-powered system that detects potholes and cracks in road surfaces using YOLOv8.</p>
        </div>
        """, unsafe_allow_html=True)
    with col2:
        st.markdown("""
        <div class="card">
            <h3>🌍 Why is it helpful?</h3>
            <p>It helps municipalities monitor infrastructure, prioritize maintenance, and allows citizens to report damage easily.</p>
        </div>
        """, unsafe_allow_html=True)

    # Damage overview chart
    reported = 120
    maintained = 85
    st.plotly_chart(create_damage_ratio_chart(reported, maintained), use_container_width=True)

    # Button to move to Detection page
    if st.button("🔍 Go to Detection Page"):
        st.session_state.page = "Detection"

# ===============================
# DETECTION PAGE
# ===============================
def detection_page():
    st.markdown("<h1>🔍 Road Damage Detection</h1>", unsafe_allow_html=True)
    st.sidebar.header("Settings")
    input_type = st.sidebar.radio("Input type", ["Image", "Video"])
    uploaded = st.file_uploader("Upload", type=["jpg","jpeg","png","webp","mp4","avi","mov","webm"])

    if uploaded is None:
        st.info("Upload file...")
        return

    model = load_model()

    if st.button("Run Detection"):
        if input_type == "Image":
            image = Image.open(uploaded).convert("RGB")
            image_array = np.array(image)
            annotated, result = run_image_detection(image_array, model)
            st.image(annotated, caption="Detected", use_container_width=True)
        else:
            with tempfile.NamedTemporaryFile(delete=False, suffix=Path(uploaded.name).suffix) as tmp:
                tmp.write(uploaded.read())
                video_path = tmp.name
            progress = st.progress(0)
            status = st.empty()
            result_path = run_video_detection(video_path, model, progress, status)
            progress.empty()
            status.empty()
            st.success("Video Processed!")
            st.video(result_path)
            st.session_state.setdefault("temp_files", []).append(result_path)

# ===============================
# NAVIGATION
# ===============================
def main():
    st.sidebar.title("Navigation")
    if "page" not in st.session_state:
        st.session_state.page = "Home"

    if st.session_state.page == "Home":
        home_page()
    else:
        detection_page()

    # Sidebar navigation override
    page_choice = st.sidebar.radio("Go to", ["Home", "Detection"], index=0 if st.session_state.page=="Home" else 1)
    st.session_state.page = page_choice

if __name__ == "__main__":
    main()
