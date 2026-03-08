import os
import logging
import base64
import cv2
import numpy as np
import torch
from ultralytics import YOLO

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

model = None


# =====================================================
# LOAD MODEL (OPTIMIZED)
# =====================================================
def load_model():
    global model

    if model is not None:
        return

    try:
        backend_dir = os.path.abspath(os.path.dirname(os.path.dirname(__file__)))
        root_dir = os.path.dirname(backend_dir)
        model_path = os.path.join(root_dir, "model", "best.pt")

        if not os.path.exists(model_path):
            logger.error(f"YOLO model not found at {model_path}")
            return

        logger.info(f"Loading YOLO model from {model_path}")

        model = YOLO(model_path)

        # Fuse layers for speed
        model.fuse()

        # GPU optimization
        if torch.cuda.is_available():
            model.to("cuda")
            logger.info("Using GPU acceleration")
        else:
            logger.info("Using CPU inference")

        # Warmup (reduces first inference delay)
        dummy = np.zeros((320, 320, 3), dtype=np.uint8)
        model(dummy, imgsz=320, verbose=False)

        logger.info("YOLO model loaded and warmed up")

    except Exception as e:
        logger.error(f"Error loading YOLO model: {e}")
        model = None


# =====================================================
# IMAGE DETECTION (FILE PATH)
# =====================================================
def detect_damage(image_path):

    global model

    if model is None:
        load_model()

    if model is None:
        return "Model Error", 0.0

    if not os.path.exists(image_path):
        return "Image Not Found", 0.0

    try:

        results = model(image_path, imgsz=640, conf=0.25, verbose=False)

        best_class = "No Damage"
        best_conf = 0.0

        for r in results:
            if r.boxes is not None and len(r.boxes):

                for box in r.boxes:
                    conf = float(box.conf[0])
                    cls_id = int(box.cls[0])
                    class_name = model.names[cls_id]

                    if conf > best_conf:
                        best_conf = conf
                        best_class = class_name

        return best_class, best_conf

    except Exception as e:
        logger.error(f"Detection error: {e}")
        return "Detection Error", 0.0


# =====================================================
# IMAGE DETECTION + ANNOTATED IMAGE
# =====================================================
def detect_damage_with_image(image_input):

    global model

    if model is None:
        load_model()

    if model is None:
        return "Model Error", 0.0, None

    try:

        # ------------------------------------------------
        # Support BOTH path and numpy frame
        # ------------------------------------------------
        if isinstance(image_input, str):

            if not os.path.exists(image_input):
                return "Image Not Found", 0.0, None

            frame = cv2.imread(image_input)

        else:
            frame = image_input

        results = model(frame, imgsz=640, conf=0.25, verbose=False)

        best_class = "No Damage"
        best_conf = 0.0
        annotated_b64 = None

        for r in results:

            if r.boxes is not None and len(r.boxes):

                for box in r.boxes:
                    conf = float(box.conf[0])
                    cls_id = int(box.cls[0])
                    class_name = model.names[cls_id]

                    if conf > best_conf:
                        best_conf = conf
                        best_class = class_name

                # Annotate only if detection exists
                annotated_bgr = r.plot()

                _, buf = cv2.imencode(
                    ".jpg",
                    annotated_bgr,
                    [cv2.IMWRITE_JPEG_QUALITY, 80]
                )

                annotated_b64 = base64.b64encode(buf).decode("utf-8")

        return best_class, best_conf, annotated_b64

    except Exception as e:
        logger.error(f"Detection error: {e}")
        return "Detection Error", 0.0, None


# =====================================================
# FAST REALTIME FRAME DETECTION
# =====================================================
def detect_damage_with_frame(frame):

    global model

    if model is None:
        load_model()

    if model is None:
        return "Model Error", 0.0, None

    try:

        # Resize for speed
        frame_small = cv2.resize(frame, (320, 320))

        results = model(frame_small, imgsz=320, conf=0.25, verbose=False)

        best_class = "No Damage"
        best_conf = 0.0
        annotated_b64 = None

        for r in results:

            if r.boxes is not None and len(r.boxes):

                for box in r.boxes:

                    conf = float(box.conf[0])
                    cls_id = int(box.cls[0])
                    class_name = model.names[cls_id]

                    if conf > best_conf:
                        best_conf = conf
                        best_class = class_name

                annotated = r.plot()

                _, buf = cv2.imencode(
                    ".jpg",
                    annotated,
                    [cv2.IMWRITE_JPEG_QUALITY, 70]
                )

                annotated_b64 = base64.b64encode(buf).decode("utf-8")

        return best_class, best_conf, annotated_b64

    except Exception as e:
        logger.error(f"Realtime detection error: {e}")
        return "Detection Error", 0.0, None


# =====================================================
# VIDEO DETECTION (GPU STREAM)
# =====================================================
def detect_video_full(video_path):

    global model

    if model is None:
        load_model()

    if model is None:
        raise RuntimeError("Model not loaded")

    if not os.path.exists(video_path):
        raise FileNotFoundError(video_path)

    BAD_LABELS = {"No Damage", "Model Error", "Detection Error", "Image Not Found"}

    frame_results = []
    best_frame_b64 = None
    best_conf = 0
    total_frames = 0

    try:

        for r in model(video_path, stream=True, verbose=False):

            total_frames += 1

            best_class = "No Damage"
            frame_conf = 0

            if r.boxes is not None and len(r.boxes):

                for box in r.boxes:

                    conf = float(box.conf[0])
                    cls_id = int(box.cls[0])
                    name = model.names[cls_id]

                    if conf > frame_conf:
                        frame_conf = conf
                        best_class = name

            frame_results.append({
                "frame": total_frames,
                "damage_type": best_class,
                "confidence": round(frame_conf, 3)
            })

            if best_class not in BAD_LABELS and frame_conf > best_conf:

                best_conf = frame_conf

                annotated = r.plot()

                _, buf = cv2.imencode(
                    ".jpg",
                    annotated,
                    [cv2.IMWRITE_JPEG_QUALITY, 85]
                )

                best_frame_b64 = base64.b64encode(buf).decode("utf-8")

    except Exception as e:
        logger.error(f"Video detection error: {e}")
        raise

    # Build summary
    counts = {}
    conf_sum = {}

    for r in frame_results:

        dt = r["damage_type"]

        if dt in BAD_LABELS:
            continue

        counts[dt] = counts.get(dt, 0) + 1
        conf_sum[dt] = conf_sum.get(dt, 0) + r["confidence"]

    summary = [
        {
            "damage_type": dt,
            "count": counts[dt],
            "avg_confidence": round(conf_sum[dt] / counts[dt], 3)
        }
        for dt in sorted(counts, key=lambda x: -counts[x])
    ]

    return {
        "total_frames": total_frames,
        "detections_found": sum(counts.values()),
        "summary": summary,
        "top_damage": summary[0]["damage_type"] if summary else "No Damage",
        "best_annotated_frame": best_frame_b64
    }