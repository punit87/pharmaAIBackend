import os
import subprocess
import sys
import io
import json
import zipfile
import torch
import layoutparser as lp
from PIL import Image
import numpy as np
import cv2

def model_fn(model_dir):
    #submit_dir = os.environ.get('SAGEMAKER_SUBMIT_DIRECTORY')
    #req_path = os.path.join(submit_dir, "requirements.txt")

    #print(f"Submit directory: {submit_dir}")
    #print(f"Requirements path: {req_path}")
    #print(f"Directory contents: {os.listdir(submit_dir)}")
    #print(f"Requirements exists: {os.path.exists(req_path)}")

    #print(f"Installing requirements from {req_path}")
    #result = subprocess.run(
        #[sys.executable, "-m", "pip", "install", "--no-cache-dir", "-r", req_path],
        #check=True,
        #capture_output=True,
        #text=True,
    #)
    #print("Requirements installed successfully.")
    #print(f"pip install output: {result.stdout}")

    # subprocess.check_call([sys.executable, "-m", "pip", "install", "-r", req_path])

   
    """Load the model from the model directory."""
    model = lp.Detectron2LayoutModel(
        config_path=os.path.join(model_dir, "config.yaml"),
        model_path=os.path.join(model_dir, "model_final.pth"),
        label_map={0: "figure", 1: "list", 2: "table", 3: "text", 4: "title"},
        extra_config=["MODEL.ROI_HEADS.SCORE_THRESH_TEST", 0.2],
        device="cpu"
    )
    return model

def input_fn(request_body, request_content_type):
    """Process ZIP file input containing a PNG image."""
    if request_content_type != "application/zip":
        raise ValueError(f"Unsupported content type: {request_content_type}")

    # Extract PNG from ZIP
    zip_io = io.BytesIO(request_body)
    with zipfile.ZipFile(zip_io, "r") as zip_ref:
        png_files = [f for f in zip_ref.namelist() if f.endswith(".png")]
        if not png_files:
            raise ValueError("No PNG file found in ZIP")
        if len(png_files) > 1:
            raise ValueError("Multiple PNG files found; expected one")
        with zip_ref.open(png_files[0]) as png_file:
            image = Image.open(png_file).convert("RGB")
            image_np = np.array(image)
            image_cv = cv2.cvtColor(image_np, cv2.COLOR_RGB2BGR)
    return image_cv

def predict_fn(data, model):
    """Run LayoutParser model to detect layout blocks."""
    layout = model.detect(data)
    # Convert layout to JSON-serializable format
    layout_blocks = [
        {
            "type": block.type.lower(),
            "coordinates": [int(coord) for coord in block.coordinates],
            "score": float(block.score) if block.score is not None else None
        }
        for block in layout
    ]
    return layout_blocks

def output_fn(prediction, accept):
    """Return JSON response."""
    if accept != "application/json":
        raise ValueError(f"Unsupported accept type: {accept}")
    return json.dumps({"layout_blocks": prediction}), "application/json"