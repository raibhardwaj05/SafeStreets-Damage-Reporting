import os
import logging
import base64
import cv2
import numpy as np
import json
import torch
import concurrent.futures
from ultralytics import YOLO

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

model = None
waterlog_model = None
accident_model = None
per_class_thresholds = None

# Global thread pool for parallel TensorRT streams
_executor = concurrent.futures.ThreadPoolExecutor(max_workers=3)

def calculate_severity(confidence, area, pothole_count=1):
    """
    Zero-latency helper to compute priority using Confidence, Bounding Box dimensions, and Count.
    """
    if pothole_count >= 3 or (area >= 0.15 and confidence >= 0.5):
        return "critical"
    elif pothole_count == 2 or (area >= 0.08 and confidence >= 0.45):
        return "high"
    elif area >= 0.02 or confidence >= 0.5:
        return "medium"
    else:
        return "low"

# =====================================================
# LOAD MODEL (OPTIMIZED)
# =====================================================
def load_model():
    global model, waterlog_model, accident_model, per_class_thresholds

    try:
        backend_dir = os.path.abspath(os.path.dirname(os.path.dirname(__file__)))
        root_dir = os.path.dirname(backend_dir)
        
        # Load thresholds if available
        if per_class_thresholds is None:
            thresh_path = os.path.join(root_dir, "per_class_thresholds.json")
            if os.path.exists(thresh_path):
                try:
                    with open(thresh_path) as f:
                        per_class_thresholds = json.load(f)
                    logger.info(f"Loaded per-class thresholds: {per_class_thresholds}")
                except Exception as e:
                    logger.error(f"Error loading thresholds: {e}")
                    per_class_thresholds = None
            else:
                logger.info("No per-class thresholds found, using default 0.25")

        # -------------------------
        # Pothole Model Load
        # -------------------------
        if model is None:
            engine_path = os.path.join(root_dir, "model", "best.engine")
            pt_path = os.path.join(root_dir, "model", "best.pt")

            if os.path.exists(engine_path):
                logger.info(f"Loading TensorRT engine from {engine_path}")
                model = YOLO(engine_path)
                
                # WARMUP FOR TENSORRT
                dummy = np.zeros((640, 640, 3), dtype=np.uint8)
                for _ in range(5):
                    model.track(dummy, imgsz=640, tracker="bytetrack.yaml", persist=True, verbose=False)
                logger.info("TensorRT model warmed up for tracking")
                
            elif os.path.exists(pt_path):
                logger.info(f"Loading PyTorch model from {pt_path}")
                model = YOLO(pt_path)
                model.fuse()
                if torch.cuda.is_available():
                    model.to("cuda")
                dummy = np.zeros((320, 320, 3), dtype=np.uint8)
                for _ in range(3):
                    model(dummy, imgsz=320, verbose=False)
                logger.info("PyTorch model warmed up")

        # -------------------------
        # Waterlogging Model Load
        # -------------------------
        if waterlog_model is None:
            waterlog_path = os.path.join(root_dir, "model", "waterlog.engine")
            if os.path.exists(waterlog_path):
                logger.info(f"Loading Waterlog TensorRT engine from {waterlog_path}")
                waterlog_model = YOLO(waterlog_path, task='detect')
                
                dummy = np.zeros((640, 640, 3), dtype=np.uint8)
                for _ in range(5):
                    waterlog_model.track(dummy, imgsz=640, tracker="bytetrack.yaml", persist=True, verbose=False)
                logger.info("Waterlog model warmed up for tracking")
            else:
                logger.warning(f"No Waterlog model found at {waterlog_path}")

        # -------------------------
        # Accident Model Load
        # -------------------------
        if accident_model is None:
            accident_path = r"C:\Users\524ta\Downloads\l\backend\model\best.engine"
            if os.path.exists(accident_path):
                logger.info(f"Loading Accident TensorRT engine from {accident_path}")
                accident_model = YOLO(accident_path, task='detect')
                
                dummy = np.zeros((640, 640, 3), dtype=np.uint8)
                for _ in range(3):
                    # Warm up only on accident classes (ignoring bike=0, car=4, person=9)
                    accident_model.track(dummy, imgsz=640, tracker="bytetrack.yaml", persist=True, verbose=False, classes=[1,2,3,5,6,7,8])
                logger.info("Accident model warmed up for tracking")
            else:
                logger.warning(f"No Accident model found at {accident_path}")

    except Exception as e:
        logger.error(f"Error loading YOLO models: {e}")

def get_threshold(class_name, default_conf=0.25):
    """Get the confidence threshold for a specific class."""
    if per_class_thresholds and class_name in per_class_thresholds:
        return per_class_thresholds[class_name]
    return default_conf
    
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
        # Use a low base confidence to let per-class thresholding work
        base_conf = min(per_class_thresholds.values()) * 0.8 if per_class_thresholds else 0.25
        results = model(image_path, imgsz=640, conf=base_conf, verbose=False)

        best_class = "No Damage"
        best_conf = 0.0
        best_area = 0.0
        pothole_count = 0

        for r in results:
            if r.boxes is not None and len(r.boxes):
                for box in r.boxes:
                    conf = float(box.conf[0])
                    cls_id = int(box.cls[0])
                    class_name = model.names[cls_id]
                    
                    # Apply per-class threshold
                    if conf >= get_threshold(class_name, 0.25):
                        pothole_count += 1
                        if conf > best_conf:
                            best_conf = conf
                            best_class = class_name
                            
                            # Extremely fast math: no latency overhead
                            norm_w = float(box.xywhn[0][2])
                            norm_h = float(box.xywhn[0][3])
                            best_area = norm_w * norm_h

        return best_class, best_conf, best_area, pothole_count

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
        if isinstance(image_input, str):
            if not os.path.exists(image_input):
                return "Image Not Found", 0.0, None
            frame = cv2.imread(image_input)
        else:
            frame = image_input

        base_conf = min(per_class_thresholds.values()) * 0.8 if per_class_thresholds else 0.25
        results = model(frame, imgsz=640, conf=base_conf, verbose=False)

        best_class = "No Damage"
        best_conf = 0.0
        best_area = 0.0
        pothole_count = 0
        annotated_b64 = None

        for r in results:
            if r.boxes is not None and len(r.boxes):
                valid_boxes = []
                for idx, box in enumerate(r.boxes):
                    conf = float(box.conf[0])
                    cls_id = int(box.cls[0])
                    class_name = model.names[cls_id]
                    
                    if conf >= get_threshold(class_name, 0.25):
                        valid_boxes.append(idx)
                        pothole_count += 1
                        if conf > best_conf:
                            best_conf = conf
                            best_class = class_name
                            best_area = float(box.xywhn[0][2]) * float(box.xywhn[0][3])

                # Annotate only if valid detection exists
                if valid_boxes:
                    # Optional: filter the plot to only show valid boxes, 
                    # but mapping indices back is tricky in Ultralytics. 
                    # We'll rely on the base_conf being close enough.
                    annotated_bgr = r.plot(conf=True)
                    _, buf = cv2.imencode(".jpg", annotated_bgr, [cv2.IMWRITE_JPEG_QUALITY, 80])
                    annotated_b64 = base64.b64encode(buf).decode("utf-8")

        return best_class, best_conf, best_area, pothole_count, annotated_b64

    except Exception as e:
        logger.error(f"Detection error: {e}")
        return "Detection Error", 0.0, 0.0, 0, None



# =====================================================
# FAST REALTIME FRAME DETECTION
# =====================================================
def detect_damage_with_frame(frame):
    """
    Optimized Dual-Model parallel execution using ThreadPoolExecutor
    Submits frames simultaneously to parallel CUDA streams for 0 added latency.
    """
    global model, waterlog_model, accident_model

    if model is None or waterlog_model is None or accident_model is None:
        load_model()

    if model is None:
        return "Model Error", 0.0, 0.0, 0, None

    try:
        base_conf = min(per_class_thresholds.values()) * 0.8 if per_class_thresholds else 0.25

        # ----------------------------------------------------
        # DISPATCH BOTH INFERENCES SIMULTANEOUSLY 
        # (Nvidia Driver routes them to concurrent CUDA Streams)
        # ----------------------------------------------------
        future_pothole = _executor.submit(
            model.track, frame, imgsz=640, conf=base_conf, tracker="bytetrack.yaml", persist=True, verbose=False
        ) if model else None

        future_waterlog = _executor.submit(
            waterlog_model.track, frame, imgsz=640, conf=0.35, tracker="bytetrack.yaml", persist=True, verbose=False
        ) if waterlog_model else None

        future_accident = _executor.submit(
            accident_model.track, frame, imgsz=640, conf=0.35, tracker="bytetrack.yaml", persist=True, verbose=False, classes=[1,2,3,5,6,7,8]
        ) if accident_model else None

        # Resolve futures
        results_pothole = future_pothole.result() if future_pothole else []
        results_waterlog = future_waterlog.result() if future_waterlog else []
        results_accident = future_accident.result() if future_accident else []

        # ----------------------------------------------------
        # AGGREGATE RESULTS
        # ----------------------------------------------------
        detected_classes = []
        pothole_count = 0
        waterlog_count = 0
        accident_count = 0
        
        best_pothole_conf = 0.0
        best_waterlog_conf = 0.0
        best_accident_conf = 0.0
        combined_area = 0.0
        
        annotated = frame.copy()
        valid_det_pothole = False
        valid_det_waterlog = False
        valid_det_accident = False
        
        track_ids = []

        # Accumulate Pothole Box Status
        if results_pothole:
            for r in results_pothole:
                if r.boxes is not None and len(r.boxes):
                    for box in r.boxes:
                        conf = float(box.conf[0])
                        cls_id = int(box.cls[0])
                        class_name = model.names[cls_id]

                        if conf >= get_threshold(class_name, 0.25):
                            valid_det_pothole = True
                            pothole_count += 1
                            combined_area += float(box.xywhn[0][2]) * float(box.xywhn[0][3])
                            if conf > best_pothole_conf:
                                best_pothole_conf = conf
                            if box.id is not None:
                                track_ids.append(f"p_{int(box.id[0])}")
                    
                    if valid_det_pothole:
                        # Draw pothole boxes on the combined annotation frame
                        try:
                            # Using img kwarg allows ultralytics to draw onto our shared array
                            annotated = r.plot(img=annotated, conf=True)
                        except:
                            pass # Safeguard

        # Accumulate Waterlog Box Status
        if results_waterlog:
            for r in results_waterlog:
                if r.boxes is not None and len(r.boxes):
                    for box in r.boxes:
                        conf = float(box.conf[0])
                        cls_id = int(box.cls[0])
                        
                        # Ensure class_name is cleanly formatted since local labels might say 'water'
                        class_name = "Waterlogging"

                        # Hardcoded reasonable threshold for water pooling
                        if conf >= 0.35:
                            valid_det_waterlog = True
                            waterlog_count += 1
                            combined_area += float(box.xywhn[0][2]) * float(box.xywhn[0][3])
                            if conf > best_waterlog_conf:
                                best_waterlog_conf = conf
                            if box.id is not None:
                                track_ids.append(f"w_{int(box.id[0])}")
                    
                    if valid_det_waterlog:
                        try:
                            annotated = r.plot(img=annotated, conf=True)
                        except:
                            pass

        # Accumulate Accident Box Status
        if results_accident:
            for r in results_accident:
                if r.boxes is not None and len(r.boxes):
                    for box in r.boxes:
                        conf = float(box.conf[0])
                        # The tracking call filters classes, so we know it's an accident class
                        if conf >= 0.35:
                            valid_det_accident = True
                            accident_count += 1
                            combined_area += float(box.xywhn[0][2]) * float(box.xywhn[0][3])
                            if conf > best_accident_conf:
                                best_accident_conf = conf
                            if box.id is not None:
                                track_ids.append(f"a_{int(box.id[0])}")
                    
                    if valid_det_accident:
                        try:
                            # It only plots the filtered accident classes
                            annotated = r.plot(img=annotated, conf=True)
                        except:
                            pass

        annotated_b64 = None
        if valid_det_pothole or valid_det_waterlog or valid_det_accident:
            _, buf = cv2.imencode(".jpg", annotated, [cv2.IMWRITE_JPEG_QUALITY, 70])
            annotated_b64 = base64.b64encode(buf).decode("utf-8")

        # Build Response
        if pothole_count > 0:
            detected_classes.append("Pothole")
        if waterlog_count > 0:
            detected_classes.append("Waterlogging")
        if accident_count > 0:
            detected_classes.append("Accident")
            
        best_class = ", ".join(detected_classes) if detected_classes else "No Damage"
        best_conf = max(best_pothole_conf, best_waterlog_conf, best_accident_conf)

        return best_class, best_conf, combined_area, (pothole_count + waterlog_count + accident_count), annotated_b64, track_ids

    except Exception as e:
        logger.error(f"Realtime parallel detection error: {e}")
        return "Detection Error", 0.0, 0.0, 0, None


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