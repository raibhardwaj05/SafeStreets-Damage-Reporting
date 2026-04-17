#!/usr/bin/env python3
"""
[A] TensorRT Export with Optimal Settings
==========================================
Exports best.pt to TensorRT .engine format for maximum inference speed on NVIDIA GPUs.
TensorRT fuses layers, prunes graph branches, and selects GPU-optimal kernels, resulting
in 2-5x faster inference vs PyTorch (.pt). FP16 (half precision) cuts memory bandwidth
in half with negligible accuracy loss (<0.5% mAP drop on most models).

    dynamic=True  — allows variable input sizes at slight speed cost. Use it when you
                    need to switch between imgsz values without re-exporting. For fixed
                    camera feeds (always same resolution), keep dynamic=False for best
                    throughput.

Expected result: 2-5x FPS improvement over .pt on the same GPU.
"""

import os
import sys
import time
import subprocess

# =====================================================
# USER CONFIG — edit these paths
# =====================================================
MODEL_PATH      = os.path.join(os.path.dirname(__file__), "model", "best.pt")
ENGINE_DIR      = os.path.join(os.path.dirname(__file__), "model")

# =====================================================
# Step 0 — verify GPU
# =====================================================
def verify_gpu():
    print("\n" + "=" * 60)
    print(" GPU VERIFICATION")
    print("=" * 60)
    try:
        result = subprocess.run(
            ["nvidia-smi"],
            capture_output=True, text=True, timeout=10
        )
        print(result.stdout)
        return True
    except FileNotFoundError:
        print("[ERROR] nvidia-smi not found. Is the NVIDIA driver installed?")
        return False
    except Exception as e:
        print(f"[ERROR] GPU check failed: {e}")
        return False


# =====================================================
# Step 1 — export to TensorRT FP16
# =====================================================
def export_tensorrt(imgsz=416, half=True, dynamic=False):
    """
    Export best.pt to a TensorRT .engine file.

    Args:
        imgsz:   input resolution (416 for speed, 640 for accuracy)
        half:    True = FP16 (recommended), False = FP32
        dynamic: True = allow variable input sizes at runtime
    Returns:
        Path to the exported .engine file
    """
    from ultralytics import YOLO

    if not os.path.exists(MODEL_PATH):
        print(f"[ERROR] Model file not found: {MODEL_PATH}")
        sys.exit(1)

    print(f"\n{'=' * 60}")
    print(f" EXPORTING TensorRT | imgsz={imgsz} | half={half} | dynamic={dynamic}")
    print(f"{'=' * 60}")

    model = YOLO(MODEL_PATH)

    start = time.time()
    engine_path = model.export(
        format="engine",
        imgsz=imgsz,
        half=half,
        dynamic=dynamic,
        device=0,
        simplify=True,       # ONNX graph simplification before TRT
        workspace=4,          # GB of GPU workspace for TRT builder
        verbose=False,
    )
    elapsed = time.time() - start

    print(f"\n[OK] Export complete in {elapsed:.1f}s")
    print(f"[OK] Engine saved to: {engine_path}")
    print(f"[OK] Engine size: {os.path.getsize(engine_path) / 1e6:.1f} MB")
    return engine_path


# =====================================================
# Step 2 — quick benchmark of the exported engine
# =====================================================
def quick_benchmark(engine_path, imgsz, n_warmup=50, n_test=100):
    """Run a quick FPS test on the exported engine."""
    import numpy as np
    from ultralytics import YOLO

    print(f"\n{'=' * 60}")
    print(f" QUICK BENCHMARK: {os.path.basename(engine_path)} @ imgsz={imgsz}")
    print(f"{'=' * 60}")

    model = YOLO(engine_path)

    dummy = np.random.randint(0, 255, (imgsz, imgsz, 3), dtype=np.uint8)

    # Warmup
    print(f"  Warming up ({n_warmup} frames)...")
    for _ in range(n_warmup):
        model(dummy, imgsz=imgsz, verbose=False)

    # Timed run
    print(f"  Benchmarking ({n_test} frames)...")
    t0 = time.perf_counter()
    for _ in range(n_test):
        model(dummy, imgsz=imgsz, verbose=False)
    elapsed = time.perf_counter() - t0

    fps = n_test / elapsed
    latency_ms = (elapsed / n_test) * 1000

    print(f"\n  Results:")
    print(f"    Average FPS:     {fps:.1f}")
    print(f"    Avg Latency:     {latency_ms:.2f} ms")
    print(f"    Total time:      {elapsed:.2f}s for {n_test} frames")
    return fps, latency_ms


# =====================================================
# MAIN
# =====================================================
if __name__ == "__main__":
    if not verify_gpu():
        print("[WARN] Continuing without GPU verification...")

    # --- Export at imgsz=416 (fast) ---
    engine_416 = export_tensorrt(imgsz=416, half=True, dynamic=False)
    fps_416, lat_416 = quick_benchmark(engine_416, imgsz=416)

    # --- Export at imgsz=640 (accurate) ---
    engine_640 = export_tensorrt(imgsz=640, half=True, dynamic=False)
    fps_640, lat_640 = quick_benchmark(engine_640, imgsz=640)

    # --- Summary ---
    print(f"\n{'=' * 60}")
    print(f" EXPORT SUMMARY")
    print(f"{'=' * 60}")
    print(f"  {'Size':<10} {'FPS':>10} {'Latency':>12} {'Engine':>40}")
    print(f"  {'-'*10} {'-'*10} {'-'*12} {'-'*40}")
    print(f"  {'416':<10} {fps_416:>10.1f} {lat_416:>10.2f} ms {os.path.basename(engine_416):>40}")
    print(f"  {'640':<10} {fps_640:>10.1f} {lat_640:>10.2f} ms {os.path.basename(engine_640):>40}")
    print()
    print("  TIP: Use imgsz=416 for real-time feeds, imgsz=640 for image analysis.")
    print()

    # =====================================================
    # TERMINAL COMMANDS (for reference)
    # =====================================================
    print("=" * 60)
    print(" EQUIVALENT TERMINAL COMMANDS")
    print("=" * 60)
    print(f"""
  # FP16 export at 416:
  yolo export model={MODEL_PATH} format=engine imgsz=416 half=True device=0

  # FP16 export at 640:
  yolo export model={MODEL_PATH} format=engine imgsz=640 half=True device=0

  # Dynamic export (variable input size):
  yolo export model={MODEL_PATH} format=engine imgsz=640 half=True dynamic=True device=0
""")
