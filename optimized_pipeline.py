#!/usr/bin/env python3
"""
COMBINED OPTIMIZED PRODUCTION PIPELINE
========================================
A single production script that combines:
  - Threaded video capture (CAP_PROP_BUFFERSIZE=1, separate thread)
  - TensorRT FP16 engine (auto-fallback to .pt)
  - ByteTrack tracking (persistent IDs, flicker reduction)
  - Per-class confidence thresholds (from calibration)
  - Rolling 30-frame FPS counter
  - Annotated display with track IDs and trails
  - Clean shutdown on 'q' or Ctrl+C
  - Full error handling

Usage:
  python optimized_pipeline.py                     # webcam
  python optimized_pipeline.py --source video.mp4  # video file
  python optimized_pipeline.py --source rtsp://... # RTSP stream
"""

import os
import sys
import json
import time
import signal
import logging
import argparse
import threading
from collections import defaultdict, deque

import cv2
import numpy as np

# =====================================================
# USER CONFIG — edit these paths
# =====================================================
BASE_DIR    = os.path.dirname(os.path.abspath(__file__))
ENGINE_PATH = os.path.join(BASE_DIR, "model", "best.engine")
MODEL_PATH  = os.path.join(BASE_DIR, "model", "best.pt")
THRESH_PATH = os.path.join(BASE_DIR, "per_class_thresholds.json")

# Default inference settings (from param tuning)
DEFAULT_CONF   = 0.35
DEFAULT_IOU    = 0.45
DEFAULT_IMGSZ  = 416
TRACKER_CONFIG = "bytetrack.yaml"

# Display settings
WINDOW_NAME = "SafeStreet Optimized Pipeline"
TRAIL_LEN   = 30      # track trail length in frames
FPS_WINDOW  = 30      # rolling FPS window

# Logging
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(message)s",
    datefmt="%H:%M:%S",
)
log = logging.getLogger("pipeline")


# =====================================================
# THREADED VIDEO CAPTURE
# =====================================================
class ThreadedCapture:
    """
    Threaded video capture that keeps only the latest frame.
    This eliminates the OpenCV buffer delay — you always get
    the most recent frame regardless of processing speed.
    """

    def __init__(self, source=0):
        self.source = source
        self.cap = None
        self.frame = None
        self.ret = False
        self.running = False
        self.lock = threading.Lock()
        self.thread = None

    def start(self):
        self.cap = cv2.VideoCapture(self.source)
        if not self.cap.isOpened():
            raise RuntimeError(f"Cannot open video source: {self.source}")

        # Minimize buffer to get latest frame
        self.cap.set(cv2.CAP_PROP_BUFFERSIZE, 1)

        # Try to set resolution (may not work on all sources)
        self.cap.set(cv2.CAP_PROP_FRAME_WIDTH, 1280)
        self.cap.set(cv2.CAP_PROP_FRAME_HEIGHT, 720)

        self.running = True
        self.thread = threading.Thread(target=self._capture_loop, daemon=True)
        self.thread.start()

        # Wait for first frame
        timeout = time.time() + 5.0
        while self.frame is None and time.time() < timeout:
            time.sleep(0.01)

        if self.frame is None:
            raise RuntimeError("Timeout waiting for first frame")

        h, w = self.frame.shape[:2]
        log.info(f"Capture started: {w}x{h} from {self.source}")
        return self

    def _capture_loop(self):
        while self.running:
            ret, frame = self.cap.read()
            if not ret:
                # Try to reconnect for streams
                if isinstance(self.source, str) and self.source.startswith("rtsp"):
                    time.sleep(1)
                    self.cap.release()
                    self.cap = cv2.VideoCapture(self.source)
                    continue
                else:
                    # End of video file
                    self.running = False
                    break

            with self.lock:
                self.ret = ret
                self.frame = frame

    def read(self):
        with self.lock:
            if self.frame is None:
                return False, None
            return self.ret, self.frame.copy()

    def stop(self):
        self.running = False
        if self.thread and self.thread.is_alive():
            self.thread.join(timeout=2)
        if self.cap:
            self.cap.release()
        log.info("Capture stopped")


# =====================================================
# MODEL LOADER
# =====================================================
def load_model():
    """Load the best available model (TensorRT > PyTorch)."""
    from ultralytics import YOLO

    if os.path.exists(ENGINE_PATH):
        log.info(f"Loading TensorRT engine: {ENGINE_PATH}")
        model = YOLO(ENGINE_PATH)
        log.info("TensorRT engine loaded")
    elif os.path.exists(MODEL_PATH):
        log.warning(f"TensorRT engine not found at {ENGINE_PATH}")
        log.info(f"Loading PyTorch model: {MODEL_PATH}")
        model = YOLO(MODEL_PATH)

        import torch
        if torch.cuda.is_available():
            model.to("cuda")
            log.info("PyTorch model on GPU")
        else:
            log.warning("No GPU detected — inference will be slow")
    else:
        raise FileNotFoundError(
            f"No model found! Expected:\n"
            f"  TensorRT: {ENGINE_PATH}\n"
            f"  PyTorch:  {MODEL_PATH}"
        )

    return model


# =====================================================
# THRESHOLD LOADER
# =====================================================
def load_thresholds():
    """Load per-class confidence thresholds if available."""
    if os.path.exists(THRESH_PATH):
        with open(THRESH_PATH) as f:
            thresholds = json.load(f)
        log.info(f"Per-class thresholds loaded: {thresholds}")
        return thresholds
    else:
        log.info(f"No per-class thresholds at {THRESH_PATH}, using global conf={DEFAULT_CONF}")
        return None


# =====================================================
# DETECTION FILTER
# =====================================================
def filter_by_class_threshold(results, model_names, thresholds):
    """
    Filter detections using per-class confidence thresholds.

    Args:
        results:    YOLO results object
        model_names: model.names dict
        thresholds: dict like {"pothole": 0.42}

    Returns:
        List of dicts with bbox, conf, class info, track_id
    """
    filtered = []

    for r in results:
        if r.boxes is None:
            continue

        boxes = r.boxes.xyxy.cpu().numpy()
        confs = r.boxes.conf.cpu().numpy()
        cls_ids = r.boxes.cls.cpu().numpy().astype(int)

        # Track IDs (may be None if not tracking)
        track_ids = None
        if r.boxes.id is not None:
            track_ids = r.boxes.id.cpu().numpy().astype(int)

        for i, (box, conf, cls_id) in enumerate(zip(boxes, confs, cls_ids)):
            class_name = model_names[cls_id]

            # Per-class threshold check
            if thresholds:
                min_conf = thresholds.get(class_name, DEFAULT_CONF)
            else:
                min_conf = DEFAULT_CONF

            if conf < min_conf:
                continue

            det = {
                "bbox": list(map(int, box)),
                "confidence": float(conf),
                "class_id": int(cls_id),
                "class_name": class_name,
                "track_id": int(track_ids[i]) if track_ids is not None else None,
            }
            filtered.append(det)

    return filtered


# =====================================================
# ANNOTATOR
# =====================================================
class Annotator:
    """Draw detections, track trails, and HUD on frames."""

    # Distinct colors for different classes
    CLASS_COLORS = {
        0: (0, 120, 255),    # orange
        1: (0, 255, 120),    # green
        2: (255, 80, 80),    # blue
        3: (180, 0, 255),    # purple
        4: (0, 255, 255),    # yellow
    }

    def __init__(self):
        self.track_history = defaultdict(lambda: deque(maxlen=TRAIL_LEN))
        self.track_colors = {}

    def _get_color(self, det):
        """Get consistent color per track or class."""
        if det["track_id"] is not None:
            tid = det["track_id"]
            if tid not in self.track_colors:
                # Hash-based color that's visually distinct
                hue = (tid * 47) % 180
                self.track_colors[tid] = tuple(
                    int(c) for c in cv2.cvtColor(
                        np.uint8([[[hue, 200, 230]]]),
                        cv2.COLOR_HSV2BGR
                    )[0][0]
                )
            return self.track_colors[tid]
        return self.CLASS_COLORS.get(det["class_id"], (200, 200, 200))

    def annotate(self, frame, detections, fps, frame_count):
        """Draw all annotations on the frame."""
        annotated = frame.copy()

        for det in detections:
            x1, y1, x2, y2 = det["bbox"]
            color = self._get_color(det)
            conf = det["confidence"]

            # Box
            cv2.rectangle(annotated, (x1, y1), (x2, y2), color, 2)

            # Label
            tid_str = f"ID:{det['track_id']} " if det.get("track_id") else ""
            label = f"{tid_str}{det['class_name']} {conf:.0%}"
            (lw, lh), baseline = cv2.getTextSize(
                label, cv2.FONT_HERSHEY_SIMPLEX, 0.55, 1
            )
            cv2.rectangle(annotated,
                          (x1, y1 - lh - baseline - 6),
                          (x1 + lw + 4, y1),
                          color, -1)
            cv2.putText(annotated, label,
                        (x1 + 2, y1 - baseline - 3),
                        cv2.FONT_HERSHEY_SIMPLEX, 0.55,
                        (255, 255, 255), 1, cv2.LINE_AA)

            # Track trail
            if det.get("track_id") is not None:
                center = ((x1 + x2) // 2, (y1 + y2) // 2)
                self.track_history[det["track_id"]].append(center)
                points = list(self.track_history[det["track_id"]])
                for j in range(1, len(points)):
                    alpha = j / len(points)
                    thickness = max(1, int(alpha * 3))
                    cv2.line(annotated, points[j-1], points[j], color, thickness)

        # HUD
        self._draw_hud(annotated, fps, len(detections), frame_count)

        return annotated

    def _draw_hud(self, frame, fps, det_count, frame_count):
        """Draw heads-up display."""
        h, w = frame.shape[:2]

        # Semi-transparent background
        overlay = frame.copy()
        cv2.rectangle(overlay, (5, 5), (280, 90), (0, 0, 0), -1)
        cv2.addWeighted(overlay, 0.6, frame, 0.4, 0, frame)

        # Text
        fps_color = (0, 255, 0) if fps > 20 else (0, 165, 255) if fps > 10 else (0, 0, 255)
        cv2.putText(frame, f"FPS: {fps:.1f}", (15, 30),
                    cv2.FONT_HERSHEY_SIMPLEX, 0.7, fps_color, 2, cv2.LINE_AA)
        cv2.putText(frame, f"Detections: {det_count}", (15, 55),
                    cv2.FONT_HERSHEY_SIMPLEX, 0.6, (200, 200, 200), 1, cv2.LINE_AA)
        cv2.putText(frame, f"Frame: {frame_count}", (15, 80),
                    cv2.FONT_HERSHEY_SIMPLEX, 0.6, (200, 200, 200), 1, cv2.LINE_AA)


# =====================================================
# MAIN PIPELINE
# =====================================================
def run_pipeline(source=0, imgsz=DEFAULT_IMGSZ, headless=False):
    """
    Main optimized detection + tracking pipeline.

    Args:
        source:   0 for webcam, path for video, rtsp:// for stream
        imgsz:    inference resolution
        headless: True to skip display (for benchmarking)
    """
    # ---- Setup ----
    model = load_model()
    thresholds = load_thresholds()
    annotator = Annotator()

    # FPS tracking
    fps_deque = deque(maxlen=FPS_WINDOW)
    fps = 0.0
    frame_count = 0
    total_detections = 0

    # Warmup
    log.info("Warming up model...")
    dummy = np.zeros((imgsz, imgsz, 3), dtype=np.uint8)
    for _ in range(20):
        model.track(dummy, imgsz=imgsz, conf=DEFAULT_CONF,
                    tracker=TRACKER_CONFIG, persist=True, verbose=False)
    log.info("Warmup complete")

    # Start capture
    capture = ThreadedCapture(source).start()

    # Signal handler for clean shutdown
    shutdown = threading.Event()

    def signal_handler(sig, frame_arg):
        log.info("Shutdown signal received")
        shutdown.set()
    signal.signal(signal.SIGINT, signal_handler)

    log.info(f"Pipeline running | imgsz={imgsz} | tracker={TRACKER_CONFIG}")
    log.info(f"Press 'q' to quit")

    # ---- Main loop ----
    try:
        while not shutdown.is_set():
            ret, frame = capture.read()
            if not ret or frame is None:
                if isinstance(source, str) and not source.startswith("rtsp"):
                    log.info("End of video file")
                    break
                time.sleep(0.01)
                continue

            frame_count += 1
            t_start = time.perf_counter()

            # ---- TRACKING INFERENCE ----
            results = model.track(
                frame,
                imgsz=imgsz,
                conf=min(thresholds.values()) * 0.8 if thresholds else DEFAULT_CONF,
                iou=DEFAULT_IOU,
                tracker=TRACKER_CONFIG,
                persist=True,
                verbose=False,
            )

            # ---- FILTER by per-class thresholds ----
            detections = filter_by_class_threshold(results, model.names, thresholds)
            total_detections += len(detections)

            # ---- FPS ----
            elapsed = time.perf_counter() - t_start
            fps_deque.append(elapsed)
            fps = len(fps_deque) / sum(fps_deque)

            # ---- DISPLAY ----
            if not headless:
                annotated = annotator.annotate(frame, detections, fps, frame_count)
                cv2.imshow(WINDOW_NAME, annotated)

                key = cv2.waitKey(1) & 0xFF
                if key == ord('q'):
                    log.info("Quit requested")
                    break
                elif key == ord('s'):
                    # Save screenshot
                    fname = f"screenshot_{frame_count}.jpg"
                    cv2.imwrite(fname, annotated)
                    log.info(f"Screenshot saved: {fname}")

            # Periodic logging
            if frame_count % 100 == 0:
                log.info(
                    f"Frame {frame_count} | FPS: {fps:.1f} | "
                    f"Avg detections: {total_detections/frame_count:.1f}/frame"
                )

    except Exception as e:
        log.error(f"Pipeline error: {e}", exc_info=True)
    finally:
        # ---- Cleanup ----
        capture.stop()
        if not headless:
            cv2.destroyAllWindows()

        # Final stats
        log.info(f"\n{'=' * 50}")
        log.info(f"Pipeline Summary:")
        log.info(f"  Total frames:      {frame_count}")
        log.info(f"  Total detections:  {total_detections}")
        log.info(f"  Avg FPS:           {fps:.1f}")
        log.info(f"  Avg detections:    {total_detections/max(frame_count,1):.1f}/frame")
        log.info(f"{'=' * 50}")


# =====================================================
# ENTRY POINT
# =====================================================
if __name__ == "__main__":
    parser = argparse.ArgumentParser(
        description="SafeStreet Optimized Detection Pipeline"
    )
    parser.add_argument(
        "--source", default="0",
        help="Video source: 0 for webcam, path/to/video.mp4, or rtsp://..."
    )
    parser.add_argument(
        "--imgsz", type=int, default=DEFAULT_IMGSZ,
        help=f"Inference image size (default: {DEFAULT_IMGSZ})"
    )
    parser.add_argument(
        "--headless", action="store_true",
        help="Run without display (for benchmarking)"
    )

    args = parser.parse_args()

    # Parse source
    source = int(args.source) if args.source.isdigit() else args.source

    # Verify GPU
    log.info("Checking GPU...")
    import subprocess
    try:
        result = subprocess.run(
            ["nvidia-smi", "--query-gpu=name,memory.used,memory.total",
             "--format=csv,noheader"],
            capture_output=True, text=True, timeout=5
        )
        log.info(f"GPU: {result.stdout.strip()}")
    except Exception:
        log.warning("Could not query GPU — inference may be slow")

    run_pipeline(source=source, imgsz=args.imgsz, headless=args.headless)
