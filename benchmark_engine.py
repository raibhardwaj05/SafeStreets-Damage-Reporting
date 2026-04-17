import time
import os
import cv2
import numpy as np
from ultralytics import YOLO

def benchmark_engine():
    engine_path = os.path.join(os.path.dirname(__file__), "model", "best.engine")
    
    if not os.path.exists(engine_path):
        print(f"Engine not found at {engine_path}")
        return

    print(f"Loading engine from {engine_path}")
    model = YOLO(engine_path, task='detect')
    print("Model loaded successfully.")

    # Benchmark resolutions
    resolutions = [(480, 480), (640, 640)]
    
    for h, w in resolutions:
        dummy_frame = np.zeros((h, w, 3), dtype=np.uint8)
        
        # Warmup
        print(f"\nRunning warmup for {w}x{h}...")
        for _ in range(10):
            _ = model(dummy_frame, verbose=False)
            
        print(f"Starting benchmark for 100 frames at {w}x{h}...")
        start_time = time.time()
        num_frames = 100
        
        for i in range(num_frames):
            _ = model(dummy_frame, verbose=False)
            
        end_time = time.time()
        total_time = end_time - start_time
        fps = num_frames / total_time
        latency = (total_time/num_frames)*1000
        
        print("-" * 30)
        print(f"Results for {w}x{h}:")
        print(f"Total time: {total_time:.4f} seconds")
        print(f"Average FPS: {fps:.2f} FPS")
        print(f"Average time per frame (Latency): {latency:.2f} ms")
        print("-" * 30)

if __name__ == "__main__":
    benchmark_engine()
