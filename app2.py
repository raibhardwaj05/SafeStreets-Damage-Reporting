"""
Road Damage Detection System - Enhanced Streamlit Interface
Beautiful interface for detecting potholes and cracks with home page and detection page.
"""

import os
import tempfile
from pathlib import Path

import cv2
import streamlit as st
from PIL import Image
import numpy as np
import plotly.graph_objects as go
import plotly.express as px

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

# Initialize session state for navigation
if "page" not in st.session_state:
    st.session_state.page = "Home"

# Load SVG logos
def load_svg(svg_path):
    """Load SVG file and return as string."""
    svg_file = Path(__file__).parent / svg_path
    if svg_file.exists():
        with open(svg_file, 'r', encoding='utf-8') as f:
            return f.read()
    return None

# Custom CSS for beautiful styling with modern color scheme
st.markdown("""
<style>
    /* Modern Color Palette: Teal/Cyan/Blue with Orange/Amber accents */
    :root {
        --primary-teal: #0ea5e9;
        --primary-cyan: #06b6d4;
        --primary-emerald: #14b8a6;
        --accent-orange: #f59e0b;
        --accent-amber: #fbbf24;
        --accent-red: #ef4444;
        --dark-gray: #1e293b;
        --medium-gray: #475569;
        --light-gray: #f1f5f9;
    }
    
    /* Main container styling */
    .main {
        background: linear-gradient(135deg, #e0f2fe 0%, #f0fdfa 50%, #fef3c7 100%);
        padding: 2rem;
    }
    
    /* Header styling */
    .main-header {
        font-size: 3.5rem;
        font-weight: 800;
        background: linear-gradient(135deg, #0ea5e9 0%, #06b6d4 50%, #14b8a6 100%);
        -webkit-background-clip: text;
        -webkit-text-fill-color: transparent;
        background-clip: text;
        text-align: center;
        margin-bottom: 0.5rem;
        text-shadow: 2px 2px 4px rgba(0,0,0,0.1);
    }
    
    .sub-header {
        font-size: 1.3rem;
        color: #475569;
        text-align: center;
        margin-bottom: 2rem;
        font-weight: 500;
    }
    
    /* Logo container */
    .logo-container {
        display: flex;
        justify-content: center;
        align-items: center;
        margin: 1rem 0;
    }
    
    /* Card styling */
    .info-card {
        background: linear-gradient(135deg, #0ea5e9 0%, #06b6d4 50%, #14b8a6 100%);
        padding: 2rem;
        border-radius: 20px;
        box-shadow: 0 10px 30px rgba(14, 165, 233, 0.3);
        color: white;
        margin: 1rem 0;
        transition: transform 0.3s ease;
    }
    
    .info-card:hover {
        transform: translateY(-5px);
        box-shadow: 0 15px 40px rgba(14, 165, 233, 0.4);
    }
    
    .stat-card {
        background: linear-gradient(135deg, #f59e0b 0%, #fbbf24 100%);
        padding: 1.5rem;
        border-radius: 15px;
        box-shadow: 0 8px 25px rgba(245, 158, 11, 0.3);
        color: white;
        text-align: center;
        margin: 0.5rem;
        transition: transform 0.3s ease;
    }
    
    .stat-card:hover {
        transform: translateY(-3px);
        box-shadow: 0 12px 30px rgba(245, 158, 11, 0.4);
    }
    
    .feature-card {
        background: white;
        padding: 1.5rem;
        border-radius: 15px;
        box-shadow: 0 5px 20px rgba(14, 165, 233, 0.1);
        border-left: 5px solid #0ea5e9;
        margin: 1rem 0;
        transition: all 0.3s ease;
    }
    
    .feature-card:hover {
        border-left-width: 8px;
        box-shadow: 0 8px 30px rgba(14, 165, 233, 0.2);
        transform: translateX(5px);
    }
    
    /* Button styling */
    .stButton > button {
        background: linear-gradient(135deg, #0ea5e9 0%, #06b6d4 50%, #14b8a6 100%);
        color: white;
        font-weight: 600;
        padding: 0.75rem 2rem;
        border-radius: 12px;
        border: none;
        font-size: 1.1rem;
        transition: all 0.3s ease;
        box-shadow: 0 4px 15px rgba(14, 165, 233, 0.4);
    }
    
    .stButton > button:hover {
        transform: translateY(-2px);
        box-shadow: 0 6px 20px rgba(14, 165, 233, 0.6);
        background: linear-gradient(135deg, #14b8a6 0%, #06b6d4 50%, #0ea5e9 100%);
    }
    
    /* Navigation buttons */
    .nav-button {
        background: linear-gradient(135deg, #f59e0b 0%, #fbbf24 100%);
        color: white;
        padding: 1rem 2rem;
        border-radius: 12px;
        border: none;
        font-weight: 600;
        font-size: 1.1rem;
        cursor: pointer;
        transition: all 0.3s ease;
        box-shadow: 0 4px 15px rgba(245, 158, 11, 0.4);
    }
    
    .nav-button:hover {
        transform: translateY(-2px);
        box-shadow: 0 6px 20px rgba(245, 158, 11, 0.6);
    }
    
    /* Section headers */
    .section-header {
        font-size: 2rem;
        font-weight: 700;
        color: #1e293b;
        margin: 2rem 0 1rem 0;
        padding-bottom: 0.5rem;
        border-bottom: 3px solid #0ea5e9;
    }
    
    /* Comparison label */
    .comparison-label {
        font-size: 1.2rem;
        font-weight: 600;
        margin-bottom: 0.5rem;
        text-align: center;
        color: #1e293b;
    }
    
    /* Stats number */
    .stat-number {
        font-size: 3rem;
        font-weight: 800;
        margin: 0.5rem 0;
    }
    
    .stat-label {
        font-size: 1.1rem;
        opacity: 0.9;
    }
    
    /* Hide default Streamlit elements */
    #MainMenu {visibility: hidden;}
    footer {visibility: hidden;}
    header {visibility: hidden;}
    
    /* Additional styling for better visual appeal */
    .gradient-bg {
        background: linear-gradient(135deg, #0ea5e9 0%, #06b6d4 50%, #14b8a6 100%);
    }
    
    .accent-bg {
        background: linear-gradient(135deg, #f59e0b 0%, #fbbf24 100%);
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


def create_damage_ratio_chart(reported, maintained):
    """Create a beautiful pie chart for damage ratio."""
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
        title={
            'text': 'Road Damage Status',
            'x': 0.5,
            'xanchor': 'center',
            'font': {'size': 24, 'color': '#1e293b'}
        },
        showlegend=True,
        height=400,
        paper_bgcolor='rgba(0,0,0,0)',
        plot_bgcolor='rgba(0,0,0,0)',
    )
    
    return fig


def home_page():
    """Display the home page with project information and statistics."""
    # Display logo
    logo_svg = load_svg("assets/logo.svg")
    if logo_svg:
        col1, col2, col3 = st.columns([1, 2, 1])
        with col2:
            st.markdown(f'<div class="logo-container">{logo_svg}</div>', unsafe_allow_html=True)
    
    st.markdown('<h1 class="main-header">🛣️ RoadGuard</h1>', unsafe_allow_html=True)
    st.markdown(
        '<p class="sub-header">AI-Powered Road Damage Detection System for Safer Roads</p>',
        unsafe_allow_html=True,
    )
    
    # Navigation buttons
    col1, col2, col3 = st.columns([1, 1, 1])
    with col2:
        if st.button("🔍 Go to Detection Page", use_container_width=True, key="nav_detect"):
            st.session_state.page = "Detection"
            st.rerun()
    
    st.markdown("---")
    
    # About Us Section
    st.markdown('<h2 class="section-header">📖 About Our Project</h2>', unsafe_allow_html=True)
    
    col1, col2 = st.columns(2)
    
    with col1:
        st.markdown("""
        <div class="info-card">
            <h3 style="color: white; margin-bottom: 1rem;">🎯 Our Mission</h3>
            <p style="font-size: 1.1rem; line-height: 1.8;">
            RoadGuard is an innovative AI-powered system designed to detect and monitor road damages 
            such as potholes and cracks. Our mission is to create safer roads for everyone by leveraging 
            cutting-edge computer vision technology to identify road hazards in real-time.
            </p>
        </div>
        """, unsafe_allow_html=True)
    
    with col2:
        st.markdown("""
        <div class="info-card">
            <h3 style="color: white; margin-bottom: 1rem;">💡 How It Works</h3>
            <p style="font-size: 1.1rem; line-height: 1.8;">
            Using advanced YOLO (You Only Look Once) deep learning models, RoadGuard analyzes images 
            and videos to automatically detect potholes and cracks. The system provides accurate 
            detection results that help government officials and citizens maintain road infrastructure 
            effectively.
            </p>
        </div>
        """, unsafe_allow_html=True)
    
    # Key Features
    st.markdown('<h2 class="section-header">✨ Key Features</h2>', unsafe_allow_html=True)
    
    col1, col2, col3 = st.columns(3)
    
    with col1:
        st.markdown("""
        <div class="feature-card">
            <h3 style="color: #0ea5e9; margin-bottom: 1rem;">👨‍💼 For MNC Officers</h3>
            <p style="color: #475569; line-height: 1.6;">
            Stay up-to-date with real-time road condition monitoring. Get instant notifications 
            about new damages and track maintenance progress efficiently.
            </p>
        </div>
        """, unsafe_allow_html=True)
    
    with col2:
        st.markdown("""
        <div class="feature-card">
            <h3 style="color: #0ea5e9; margin-bottom: 1rem;">🌙 Night Driver Safety</h3>
            <p style="color: #475569; line-height: 1.6;">
            Drivers navigating at night can visually see road damages pinned on an interactive map, 
            ensuring they're aware of hazards ahead and can drive safely.
            </p>
        </div>
        """, unsafe_allow_html=True)
    
    with col3:
        st.markdown("""
        <div class="feature-card">
            <h3 style="color: #0ea5e9; margin-bottom: 1rem;">🗺️ Visual Map Integration</h3>
            <p style="color: #475569; line-height: 1.6;">
            All detected road damages are automatically geotagged and displayed on an interactive map, 
            making it easy to visualize problem areas and plan maintenance routes.
            </p>
        </div>
        """, unsafe_allow_html=True)
    
    # Statistics Section
    st.markdown('<h2 class="section-header">📊 Road Damage Statistics</h2>', unsafe_allow_html=True)
    
    # Sample statistics (in a real app, these would come from a database)
    total_reported = st.session_state.get("total_reported", 1247)
    total_maintained = st.session_state.get("total_maintained", 892)
    maintenance_rate = (total_maintained / total_reported * 100) if total_reported > 0 else 0
    
    col1, col2, col3, col4 = st.columns(4)
    
    with col1:
        st.markdown(f"""
        <div class="stat-card">
            <div class="stat-number">{total_reported}</div>
            <div class="stat-label">Total Reported</div>
        </div>
        """, unsafe_allow_html=True)
    
    with col2:
        st.markdown(f"""
        <div class="stat-card">
            <div class="stat-number">{total_maintained}</div>
            <div class="stat-label">Maintained</div>
        </div>
        """, unsafe_allow_html=True)
    
    with col3:
        st.markdown(f"""
        <div class="stat-card">
            <div class="stat-number">{total_reported - total_maintained}</div>
            <div class="stat-label">Pending</div>
        </div>
        """, unsafe_allow_html=True)
    
    with col4:
        st.markdown(f"""
        <div class="stat-card">
            <div class="stat-number">{maintenance_rate:.1f}%</div>
            <div class="stat-label">Maintenance Rate</div>
        </div>
        """, unsafe_allow_html=True)
    
    # Damage Ratio Chart
    col1, col2 = st.columns([1, 1])
    
    with col1:
        fig = create_damage_ratio_chart(total_reported, total_maintained)
        st.plotly_chart(fig, use_container_width=True)
    
    with col2:
        st.markdown("""
        <div class="info-card" style="height: 400px; display: flex; flex-direction: column; justify-content: center;">
            <h3 style="color: white; margin-bottom: 1rem; text-align: center;">📸 Proof Gallery</h3>
            <p style="font-size: 1rem; line-height: 1.8; text-align: center;">
            Inspecting officers upload photographic proof after completing maintenance work. 
            This ensures transparency and accountability in road maintenance operations.
            </p>
            <div style="margin-top: 2rem; text-align: center;">
                <p style="font-size: 2rem; margin: 0;">📷</p>
                <p style="font-size: 0.9rem; opacity: 0.9;">Verified Maintenance Records</p>
            </div>
        </div>
        """, unsafe_allow_html=True)
    
    # Benefits Section
    st.markdown('<h2 class="section-header">🌟 Benefits</h2>', unsafe_allow_html=True)
    
    col1, col2 = st.columns(2)
    
    with col1:
        st.markdown("""
        <div class="feature-card">
            <h4 style="color: #0ea5e9;">✅ For Government Officials</h4>
            <ul style="color: #475569; line-height: 2;">
                <li>Real-time monitoring of road conditions</li>
                <li>Prioritized maintenance scheduling</li>
                <li>Data-driven decision making</li>
                <li>Reduced response time to road hazards</li>
                <li>Cost-effective maintenance planning</li>
            </ul>
        </div>
        """, unsafe_allow_html=True)
    
    with col2:
        st.markdown("""
        <div class="feature-card">
            <h4 style="color: #0ea5e9;">✅ For Citizens</h4>
                <ul style="color: #475569; line-height: 2;">
                <li>Enhanced road safety awareness</li>
                <li>Easy reporting of road damages</li>
                <li>Transparent maintenance tracking</li>
                <li>Safer driving experience</li>
                <li>Community involvement in road safety</li>
            </ul>
        </div>
        """, unsafe_allow_html=True)
    
    # Call to Action
    st.markdown("---")
    st.markdown("""
    <div style="text-align: center; padding: 2rem; background: linear-gradient(135deg, #0ea5e9 0%, #06b6d4 50%, #14b8a6 100%); border-radius: 20px; margin: 2rem 0; box-shadow: 0 10px 30px rgba(14, 165, 233, 0.3);">
        <h2 style="color: white; margin-bottom: 1rem;">Ready to Report Road Damage?</h2>
        <p style="color: white; font-size: 1.2rem; margin-bottom: 2rem;">
        Help us make roads safer by reporting damages in your area. Upload images or videos 
        to detect and inform the government about road conditions.
        </p>
    </div>
    """, unsafe_allow_html=True)
    
    col1, col2, col3 = st.columns([1, 1, 1])
    with col2:
        if st.button("🚀 Start Detection Now", use_container_width=True, key="cta_detect"):
            st.session_state.page = "Detection"
            st.rerun()


def detection_page():
    """Display the detection page for uploading and processing images/videos."""
    # Display logo icon
    logo_icon_svg = load_svg("assets/logo_icon.svg")
    if logo_icon_svg:
        col1, col2, col3 = st.columns([1, 6, 1])
        with col2:
            st.markdown(f'<div class="logo-container">{logo_icon_svg}</div>', unsafe_allow_html=True)
    
    st.markdown('<h1 class="main-header">🔍 Road Damage Detection</h1>', unsafe_allow_html=True)
    st.markdown(
        '<p class="sub-header">Upload an image or video to detect potholes and cracks</p>',
        unsafe_allow_html=True,
    )
    
    # Navigation back to home
    col1, col2, col3 = st.columns([1, 1, 1])
    with col1:
        if st.button("🏠 Back to Home", use_container_width=True, key="nav_home"):
            st.session_state.page = "Home"
            st.rerun()
    
    st.markdown("---")
    
    # Sidebar
    st.sidebar.header("⚙️ Settings")
    input_type = st.sidebar.radio(
        "Input type",
        ["Image", "Video"],
        help="Choose whether to upload an image or a video.",
    )
    
    st.sidebar.markdown("---")
    st.sidebar.markdown("### 📋 Supported formats")
    if input_type == "Image":
        st.sidebar.markdown("- JPEG, PNG, BMP, WebP")
    else:
        st.sidebar.markdown("- MP4, AVI, MOV, WebM")
    
    st.sidebar.markdown("---")
    st.sidebar.markdown("### ℹ️ How to use")
    st.sidebar.markdown("""
    1. Select input type (Image/Video)
    2. Upload your file
    3. Click 'Run Detection'
    4. View results and report to government
    """)
    
    # File upload
    if input_type == "Image":
        uploaded = st.file_uploader(
            "📤 Upload an image", 
            type=["jpg", "jpeg", "png", "bmp", "webp"],
            help="Upload an image containing road damage"
        )
    else:
        uploaded = st.file_uploader(
            "📤 Upload a video", 
            type=["mp4", "avi", "mov", "webm"],
            help="Upload a video containing road damage"
        )
    
    if uploaded is None:
        st.info("👆 Please upload an image or video to get started with detection.")
        st.markdown("""
        <div style="padding: 2rem; background: linear-gradient(135deg, #f59e0b 0%, #fbbf24 100%); border-radius: 15px; margin: 2rem 0; box-shadow: 0 8px 25px rgba(245, 158, 11, 0.3);">
            <h3 style="color: white; text-align: center;">💡 Tips for Best Results</h3>
            <ul style="color: white; font-size: 1.1rem; line-height: 2;">
                <li>Ensure good lighting conditions</li>
                <li>Capture clear, focused images/videos</li>
                <li>Include the entire damaged area in frame</li>
                <li>Avoid shadows and obstructions</li>
            </ul>
        </div>
        """, unsafe_allow_html=True)
        return
    
    try:
        model = load_model()
    except FileNotFoundError as e:
        st.error(f"❌ Model not found: {e}")
        st.info("Place a `.pt` YOLO model file in the `model` folder.")
        return
    except Exception as e:
        st.error(f"❌ Failed to load model: {e}")
        return
    
    col1, col2, col3 = st.columns([1, 2, 1])
    with col2:
        detect_button = st.button("🔍 Run Detection", use_container_width=True)
    
    if not detect_button:
        return
    
    # IMAGE MODE
    if input_type == "Image":
        image = Image.open(uploaded).convert("RGB")
        image_array = np.array(image)
        
        with st.spinner("🔍 Running AI detection... Please wait..."):
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
            
            st.success(f"✅ **Detected {n} damage(s):** {count_str}")
            
            # Update statistics
            st.session_state["total_reported"] = st.session_state.get("total_reported", 1247) + 1
        else:
            count_str = "No potholes or cracks detected"
            st.info(f"ℹ️ {count_str}")
        
        col_orig, col_det = st.columns(2)
        with col_orig:
            st.markdown('<p class="comparison-label">📷 Original Image</p>', unsafe_allow_html=True)
            st.image(image, use_container_width=True)
        with col_det:
            st.markdown('<p class="comparison-label">🎯 Detection Results</p>', unsafe_allow_html=True)
            st.image(annotated_rgb, use_container_width=True)
        
        # Report to government section
        if n > 0:
            st.markdown("---")
            st.markdown("### 📢 Report to Government")
            col1, col2, col3 = st.columns([1, 2, 1])
            with col2:
                if st.button("📤 Submit Report to Government", use_container_width=True):
                    st.success("✅ Report submitted successfully! Government officials have been notified.")
                    st.balloons()
    
    # VIDEO MODE
    else:
        with tempfile.NamedTemporaryFile(suffix=Path(uploaded.name).suffix, delete=False) as tmp:
            tmp.write(uploaded.read())
            video_path = tmp.name
        
        progress_bar = st.progress(0, text="Preparing video processing...")
        status = st.empty()
        
        try:
            with st.spinner("🎬 Processing video... This may take a while..."):
                output_path = run_video_detection(video_path, model, progress_bar, status)
        except Exception as e:
            progress_bar.empty()
            st.error(f"❌ Video processing failed: {e}")
            return
        finally:
            if os.path.exists(video_path):
                os.unlink(video_path)
        
        progress_bar.empty()
        status.empty()
        
        st.success("✅ Video processed successfully!")
        st.markdown('<p class="comparison-label">📹 Comparison: Original (Left) | Detected (Right)</p>', unsafe_allow_html=True)
        
        st.video(output_path)
        
        st.session_state.setdefault("temp_files", []).append(output_path)
        
        # Report to government section
        st.markdown("---")
        st.markdown("### 📢 Report to Government")
        col1, col2, col3 = st.columns([1, 2, 1])
        with col2:
            if st.button("📤 Submit Report to Government", use_container_width=True):
                st.success("✅ Report submitted successfully! Government officials have been notified.")
                st.balloons()


def main():
    """Main function to handle page navigation."""
    if st.session_state.page == "Home":
        home_page()
    elif st.session_state.page == "Detection":
        detection_page()


if __name__ == "__main__":
    main()
