# ============================
# RoadGuard — Streamlit App
# Side-by-Side Video (No OpenCV)
# ============================

import os
import tempfile
from pathlib import Path
import numpy as np
import imageio
import streamlit as st
from PIL import Image
import plotly.graph_objects as go

# Environment variables for headless mode
os.environ["YOLO_HEADLESS"] = "True"
os.environ["OPENCV_VIDEOIO_PRIORITY_MSMF"] = "0"

from ultralytics import YOLO

# Page config
st.set_page_config(
    page_title="RoadGuard - Road Damage Detection System",
    page_icon="🛣️",
    layout="wide",
    initial_sidebar_state="expanded",
)

# Cleanup old temp files safely at app start
for f in st.session_state.get("temp_files", []):
    try:
        os.unlink(f)
    except:
        pass
st.session_state["temp_files"] = []

if "page" not in st.session_state:
    st.session_state.page = "Home"

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
    annotated_pil = results[0].plot(pil=True)  # PIL image
    annotated_rgb = np.array(annotated_pil)    # Already RGB
    return annotated_rgb, results[0]

# ===============================
# VIDEO PROCESSOR (SIDE-BY-SIDE)
# ===============================
def run_video_detection(video_path, model, progress_bar=None, status=None):
    reader = imageio.get_reader(video_path)
    fps = reader.get_meta_data().get("fps", 24)
    frames = []

    total_frames = reader.count_frames() if hasattr(reader, "count_frames") else None
    frame_idx = 0

    # temp output video
    with tempfile.NamedTemporaryFile(suffix=".mp4", delete=False) as tmp:
        output_path = tmp.name

    # iterate frames
    for frame in reader:
        frame_rgb = frame  # Already RGB

        # YOLO expects BGR
        frame_bgr = frame_rgb[..., ::-1]

        results = model(frame_bgr, conf=0.1, iou=0.5, verbose=False)
        annotated_pil = results[0].plot(pil=True)   # PIL image
        annotated_rgb = np.array(annotated_pil)     # Already RGB

        # Side-by-side horizontally
        combined = np.hstack((frame_rgb, annotated_rgb))
        frames.append(combined)

        frame_idx += 1
        if progress_bar and total_frames:
            progress = frame_idx / total_frames
            progress_bar.progress(progress, text=f"Processing {frame_idx}/{total_frames}")

    reader.close()

    # Write out video
    writer = imageio.get_writer(output_path, fps=fps, codec="libx264", macro_block_size=None)
    for f in frames:
        writer.append_data(f)
    writer.close()

    return output_path

# ===============================
# PLOTLY PIE CHART (unchanged)
# ===============================
def create_damage_ratio_chart(reported, maintained):
    labels = ['Maintained', 'Pending']
    values = [maintained, reported - maintained]
    colors = ['#14b8a6', '#f59e0b']
    fig = go.Figure(data=[go.Pie(
        labels=labels,
        values=values,
        hole=0.4,
        marker_colors=colors,
        textinfo='label+percent',
        textfont_size=16,
        marker=dict(line=dict(color='#FFFFFF', width=3))
    )])
    fig.update_layout(
        title={'text': 'Road Damage Status', 'x': 0.5},
        showlegend=True,
        height=400,
        paper_bgcolor='rgba(0,0,0,0)',
        plot_bgcolor='rgba(0,0,0,0)',
    )
    return fig

# ===============================
# DETECTION PAGE (UI)
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

        else:  # VIDEO
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
    detection_page()  # For demo: always go to detection

if __name__ == "__main__":
    main()
