#!/usr/bin/env python3
"""
[I] ByteTrack / BoTSORT Tracking Integration
===============================================
Tracking assigns persistent IDs to detected objects across frames. This has TWO
major benefits:
  1. REDUCES FALSE POSITIVES: A detection that appears for only 1 frame is likely
     noise. Tracked objects must persist across multiple frames, filtering flickers.
  2. SMOOTH TRAJECTORIES: Instead of jittery per-frame detections, you get smooth
     bounding box tracks that look professional.

ByteTrack (default in Ultralytics) is fastest. BoTSORT adds appearance features for
better re-identification after occlusion but is slightly slower.

Expected result: ~30% fewer false positive detections, stable track IDs, minimal
speed impact (<5% FPS reduction).
"""

import os
import sys
import time
from collections import defaultdict

import cv2
import numpy as np

# =====================================================
# USER CONFIG
# =====================================================
MODEL_PATH   = os.path.join(os.path.dirname(__file__), "model", "best.pt")
ENGINE_PATH  = os.path.join(os.path.dirname(__file__), "model", "best.engine")
VIDEO_SOURCE = 0  # 0 for webcam, or path to video file
IMGSZ        = 416
CONF         = 0.35
IOU          = 0.45

# Tracker config: "bytetrack.yaml" or "botsort.yaml"
TRACKER      = "bytetrack.yaml"


def get_model():
    """Load best available model (TensorRT > PyTorch)."""
    from ultralytics import YOLO

    if os.path.exists(ENGINE_PATH):
        print(f"[OK] Using TensorRT engine: {ENGINE_PATH}")
        return YOLO(ENGINE_PATH)
    elif os.path.exists(MODEL_PATH):
        print(f"[OK] Using PyTorch model: {MODEL_PATH}")
        return YOLO(MODEL_PATH)
    else:
        print(f"[ERROR] No model found!")
        sys.exit(1)


def tracking_demo_predict_vs_track():
    """
    Compare model.predict() vs model.track() to show how tracking
    smooths out false positives.
    """
    from ultralytics import YOLO

    model = get_model()

    print(f"\n{'=' * 60}")
    print(f" PREDICT vs TRACK COMPARISON")
    print(f" Source: {VIDEO_SOURCE}")
    print(f"{'=' * 60}")

    cap = cv2.VideoCapture(VIDEO_SOURCE)
    if not cap.isOpened():
        print(f"[ERROR] Could not open video source: {VIDEO_SOURCE}")
        print(f"        Set VIDEO_SOURCE to a video file path or 0 for webcam.")
        return

    cap.set(cv2.CAP_PROP_BUFFERSIZE, 1)

    predict_det_counts = []
    track_det_counts = []
    predict_times = []
    track_times = []

    frame_count = 0
    max_frames = 200

    print(f"  Running {max_frames} frames...")

    while frame_count < max_frames:
        ret, frame = cap.read()
        if not ret:
            cap.set(cv2.CAP_PROP_POS_FRAMES, 0)
            continue

        frame_count += 1

        # --- predict() ---
        t0 = time.perf_counter()
        pred_results = model.predict(
            frame, imgsz=IMGSZ, conf=CONF, iou=IOU, verbose=False
        )
        predict_times.append(time.perf_counter() - t0)

        pred_count = 0
        for r in pred_results:
            if r.boxes is not None:
                pred_count += len(r.boxes)
        predict_det_counts.append(pred_count)

        # --- track() ---
        t0 = time.perf_counter()
        track_results = model.track(
            frame,
            imgsz=IMGSZ,
            conf=CONF,
            iou=IOU,
            tracker=TRACKER,
            persist=True,
            verbose=False,
        )
        track_times.append(time.perf_counter() - t0)

        track_count = 0
        for r in track_results:
            if r.boxes is not None:
                track_count += len(r.boxes)
        track_det_counts.append(track_count)

    cap.release()

    # Stats
    avg_pred_dets = sum(predict_det_counts) / len(predict_det_counts)
    avg_track_dets = sum(track_det_counts) / len(track_det_counts)
    avg_pred_fps = 1.0 / (sum(predict_times) / len(predict_times))
    avg_track_fps = 1.0 / (sum(track_times) / len(track_times))

    # Count "flickers" — frames where detection appears then disappears
    pred_flickers = sum(1 for i in range(1, len(predict_det_counts))
                        if predict_det_counts[i] != predict_det_counts[i-1])
    track_flickers = sum(1 for i in range(1, len(track_det_counts))
                         if track_det_counts[i] != track_det_counts[i-1])

    print(f"\n  {'Metric':<25} {'predict()':>12} {'track()':>12}")
    print(f"  {'-'*25} {'-'*12} {'-'*12}")
    print(f"  {'Avg detections/frame':<25} {avg_pred_dets:>12.1f} {avg_track_dets:>12.1f}")
    print(f"  {'Detection flickers':<25} {pred_flickers:>12d} {track_flickers:>12d}")
    print(f"  {'FPS':<25} {avg_pred_fps:>12.1f} {avg_track_fps:>12.1f}")
    print(f"  {'Flicker reduction':<25} {'':<12} {(1 - track_flickers/(pred_flickers+1))*100:>11.0f}%")


def tracking_inference_loop():
    """
    Complete tracking inference loop with visualization.
    This is the production-ready tracking implementation.
    """
    model = get_model()

    print(f"\n{'=' * 60}")
    print(f" TRACKING INFERENCE LOOP")
    print(f" Tracker: {TRACKER}")
    print(f" Source:  {VIDEO_SOURCE}")
    print(f" Press 'q' to quit")
    print(f"{'=' * 60}")

    cap = cv2.VideoCapture(VIDEO_SOURCE)
    if not cap.isOpened():
        print(f"[ERROR] Could not open: {VIDEO_SOURCE}")
        return

    cap.set(cv2.CAP_PROP_BUFFERSIZE, 1)

    # Track history for trails
    track_history = defaultdict(list)
    fps_times = []
    frame_count = 0

    # Color palette for track IDs
    colors = {}

    try:
        while True:
            ret, frame = cap.read()
            if not ret:
                break

            frame_count += 1
            t0 = time.perf_counter()

            # ---- TRACKING INFERENCE ----
            results = model.track(
                frame,
                imgsz=IMGSZ,
                conf=CONF,
                iou=IOU,
                tracker=TRACKER,
                persist=True,         # maintain tracks across frames
                verbose=False,
            )

            # ---- DRAW RESULTS ----
            annotated = frame.copy()

            for r in results:
                if r.boxes is None or r.boxes.id is None:
                    continue

                boxes = r.boxes.xyxy.cpu().numpy()
                confs = r.boxes.conf.cpu().numpy()
                cls_ids = r.boxes.cls.cpu().numpy().astype(int)
                track_ids = r.boxes.id.cpu().numpy().astype(int)

                for box, conf, cls_id, track_id in zip(boxes, confs, cls_ids, track_ids):
                    x1, y1, x2, y2 = map(int, box)
                    class_name = model.names[cls_id]

                    # Consistent color per track ID
                    if track_id not in colors:
                        colors[track_id] = (
                            int(hash(str(track_id)) % 256),
                            int(hash(str(track_id * 2)) % 256),
                            int(hash(str(track_id * 3)) % 256),
                        )
                    color = colors[track_id]

                    # Draw box
                    cv2.rectangle(annotated, (x1, y1), (x2, y2), color, 2)

                    # Label with track ID
                    label = f"ID:{track_id} {class_name} {conf:.2f}"
                    (lw, lh), _ = cv2.getTextSize(
                        label, cv2.FONT_HERSHEY_SIMPLEX, 0.5, 1
                    )
                    cv2.rectangle(annotated, (x1, y1 - lh - 10), (x1 + lw, y1), color, -1)
                    cv2.putText(annotated, label, (x1, y1 - 5),
                                cv2.FONT_HERSHEY_SIMPLEX, 0.5, (255, 255, 255), 1)

                    # Track trail
                    center = ((x1 + x2) // 2, (y1 + y2) // 2)
                    track_history[track_id].append(center)
                    if len(track_history[track_id]) > 30:
                        track_history[track_id].pop(0)

                    # Draw trail
                    points = track_history[track_id]
                    for j in range(1, len(points)):
                        thickness = max(1, int(j / 5))
                        cv2.line(annotated, points[j-1], points[j], color, thickness)

            # FPS counter
            elapsed = time.perf_counter() - t0
            fps_times.append(elapsed)
            if len(fps_times) > 30:
                fps_times.pop(0)
            fps = len(fps_times) / sum(fps_times)

            cv2.putText(annotated, f"FPS: {fps:.1f} | Tracker: {TRACKER}",
                        (10, 30), cv2.FONT_HERSHEY_SIMPLEX, 0.7, (0, 255, 0), 2)
            cv2.putText(annotated, f"Tracks: {len(track_history)}",
                        (10, 60), cv2.FONT_HERSHEY_SIMPLEX, 0.7, (0, 255, 0), 2)

            cv2.imshow("YOLOv8 Tracking", annotated)

            if cv2.waitKey(1) & 0xFF == ord('q'):
                break

    except KeyboardInterrupt:
        pass
    finally:
        cap.release()
        cv2.destroyAllWindows()
        print(f"\n  Processed {frame_count} frames.")
        print(f"  Total unique tracks: {len(colors)}")


if __name__ == "__main__":
    import argparse

    parser = argparse.ArgumentParser(description="YOLOv8 Tracking Demo")
    parser.add_argument("--compare", action="store_true",
                        help="Run predict vs track comparison")
    parser.add_argument("--source", default=None,
                        help="Video source (0 for webcam, or file path)")
    parser.add_argument("--tracker", default="bytetrack.yaml",
                        choices=["bytetrack.yaml", "botsort.yaml"],
                        help="Tracker to use")
    args = parser.parse_args()

    if args.source is not None:
        VIDEO_SOURCE = int(args.source) if args.source.isdigit() else args.source
    if args.tracker:
        TRACKER = args.tracker

    if args.compare:
        tracking_demo_predict_vs_track()
    else:
        tracking_inference_loop()
