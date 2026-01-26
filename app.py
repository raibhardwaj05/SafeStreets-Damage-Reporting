"""
Pothole & Crack Detection - Streamlit Interface
Uses YOLO model (best.pt) for detecting potholes and cracks in images and videos.
"""

import os
import tempfile
from pathlib import Path

import cv2
import streamlit as st
from PIL import Image
import numpy as np

# Page config
st.set_page_config(
    page_title="Pothole & Crack Detector",
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

# Custom CSS for better styling
st.markdown("""
<style>
    .main-header {
        font-size: 2.2rem;
        font-weight: 700;
        color: #1e88e5;
        margin-bottom: 0.5rem;
        text-align: center;
    }
    .sub-header {
        font-size: 1rem;
        color: #666;
        text-align: center;
        margin-bottom: 2rem;
    }
    .comparison-label {
        font-size: 1.1rem;
        font-weight: 600;
        margin-bottom: 0.5rem;
        text-align: center;
    }
    .stButton > button {
        width: 100%;
        background: linear-gradient(90deg, #1e88e5, #1565c0);
        color: white;
        font-weight: 600;
        padding: 0.6rem 1.2rem;
        border-radius: 8px;
        border: none;
    }
    .stButton > button:hover {
        background: linear-gradient(90deg, #1565c0, #0d47a1);
        color: white;
    }
</style>
""", unsafe_allow_html=True)

# Model directory
MODEL_DIR = Path(__file__).parent / "model"


def get_model_path():
    """Find the .pt model file in the model directory."""
    if not MODEL_DIR.exists():
        return None
    pt_files = list(MODEL_DIR.glob("*.pt"))
    return str(pt_files[0]) if pt_files else None


@st.cache_resource
def load_model():
    """Load YOLO model once and cache it."""
    from ultralytics import YOLO

    model_path = get_model_path()
    if not model_path:
        raise FileNotFoundError(f"No .pt model found in {MODEL_DIR}")
    st.write(f"Loaded model: {model_path}")
    return YOLO(model_path)


def run_image_detection(image_array, model):
    """Run detection on image and return original + annotated result."""
    results = model(image_array, conf=0.1, iou=0.5, verbose=False)
    annotated = results[0].plot()  # BGR -> image with boxes
    annotated_rgb = cv2.cvtColor(annotated, cv2.COLOR_BGR2RGB)
    return annotated_rgb, results[0]


def run_video_detection(video_path, model, progress_bar, status_placeholder):
    """Process video frame-by-frame, create side-by-side output."""
    cap = cv2.VideoCapture(video_path)
    if not cap.isOpened():
        raise ValueError("Could not open video file")

    fps = int(cap.get(cv2.CAP_PROP_FPS)) or 24
    width = int(cap.get(cv2.CAP_PROP_FRAME_WIDTH))
    height = int(cap.get(cv2.CAP_PROP_FRAME_HEIGHT))
    total_frames = int(cap.get(cv2.CAP_PROP_FRAME_COUNT))

    out_width = width * 2
    fourcc = cv2.VideoWriter_fourcc(*"avc1")  # H.264 compatible

    with tempfile.NamedTemporaryFile(suffix=".mp4", delete=False) as tmp:
        output_path = tmp.name

    out = cv2.VideoWriter(output_path, fourcc, fps, (out_width, height))

    frame_idx = 0
    try:
        while True:
            ret, frame = cap.read()
            if not ret:
                break

            results = model(frame, conf=0.1, iou=0.5, verbose=False)
            annotated = results[0].plot()

            if annotated.shape[:2] != (height, width):
                annotated = cv2.resize(annotated, (width, height))

            combined = np.hstack([frame, annotated])
            out.write(combined)

            frame_idx += 1
            if progress_bar and total_frames > 0:
                progress = frame_idx / total_frames
                progress_bar.progress(progress, text=f"Processing frame {frame_idx}/{total_frames}")
    finally:
        cap.release()
        out.release()

    return output_path


def main():
    st.markdown('<p class="main-header">🛣️ Pothole & Crack Detector</p>', unsafe_allow_html=True)
    st.markdown(
        '<p class="sub-header">Upload an image or video to detect potholes and cracks. '
        "Comparisons are shown side-by-side (Original | Detected).</p>",
        unsafe_allow_html=True,
    )

    # Sidebar
    st.sidebar.header("⚙️ Settings")
    input_type = st.sidebar.radio(
        "Input type",
        ["Image", "Video"],
        help="Choose whether to upload an image or a video.",
    )

    st.sidebar.markdown("---")
    st.sidebar.markdown("### Supported formats")
    if input_type == "Image":
        st.sidebar.markdown("- JPEG, PNG, BMP, WebP")
    else:
        st.sidebar.markdown("- MP4, AVI, MOV, WebM")

    # File upload
    if input_type == "Image":
        uploaded = st.file_uploader("Upload an image", type=["jpg", "jpeg", "png", "bmp", "webp"])
    else:
        uploaded = st.file_uploader("Upload a video", type=["mp4", "avi", "mov", "webm"])

    if uploaded is None:
        st.info("👆 Upload an image or video to get started.")
        return

    try:
        model = load_model()
    except FileNotFoundError as e:
        st.error(f"Model not found: {e}")
        st.info("Place a `.pt` YOLO model file in the `model` folder.")
        return
    except Exception as e:
        st.error(f"Failed to load model: {e}")
        return

    col1, col2, col3 = st.columns([1, 2, 1])
    with col2:
        detect_button = st.button("🔍 Run detection", use_container_width=True)

    if not detect_button:
        return

    # IMAGE MODE
    if input_type == "Image":
        image = Image.open(uploaded).convert("RGB")
        image_array = np.array(image)

        with st.spinner("Running detection..."):
            annotated_rgb, result = run_image_detection(image_array, model)

        boxes = result.boxes
        n = len(boxes) if boxes is not None else 0

        if n > 0:
            classes = result.names
            counts = {}
            for box in boxes:
                cls_id = int(box.cls[0])
                name = classes.get(cls_id, "object")
                counts[name] = counts.get(name, 0) + 1
            count_str = ", ".join(f"{k}: {v}" for k, v in counts.items())
        else:
            count_str = "No potholes or cracks detected"

        st.caption(f"**Detections:** {count_str}")

        col_orig, col_det = st.columns(2)
        with col_orig:
            st.markdown('<p class="comparison-label">Original</p>', unsafe_allow_html=True)
            st.image(image, use_container_width=True)
        with col_det:
            st.markdown('<p class="comparison-label">Detected (Potholes & Cracks)</p>', unsafe_allow_html=True)
            st.image(annotated_rgb, use_container_width=True)

    # VIDEO MODE
    else:
        with tempfile.NamedTemporaryFile(suffix=Path(uploaded.name).suffix, delete=False) as tmp:
            tmp.write(uploaded.read())
            video_path = tmp.name

        progress_bar = st.progress(0, text="Preparing...")
        status = st.empty()

        try:
            with st.spinner("Processing video..."):
                output_path = run_video_detection(video_path, model, progress_bar, status)
        except Exception as e:
            progress_bar.empty()
            st.error(f"Video processing failed: {e}")
            return
        finally:
            if os.path.exists(video_path):
                os.unlink(video_path)

        progress_bar.empty()
        status.empty()

        st.success("Video processed. Original (left) | Detected (right)")
        st.markdown('<p class="comparison-label">Comparison: Original | Detected</p>', unsafe_allow_html=True)

        st.video(output_path)

        st.session_state.setdefault("temp_files", []).append(output_path)


if __name__ == "__main__":
    main()
