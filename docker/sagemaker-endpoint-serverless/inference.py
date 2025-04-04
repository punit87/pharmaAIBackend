import json
import logging
import sys
import os
from sentence_transformers import SentenceTransformer
import faiss
import numpy as np
import torch
import hashlib
import re

# Set up logging for CloudWatch
logger = logging.getLogger(__name__)
logger.setLevel(logging.INFO)
handler = logging.StreamHandler(sys.stdout)
handler.setFormatter(logging.Formatter('%(asctime)s - %(name)s - %(levelname)s - %(message)s'))
logger.addHandler(handler)

# Global variables
device = torch.device("cpu")  # Serverless doesn't support GPU
sentence_model = None

# Base directory for FAISS indexes in SageMaker model directory
FAISS_BASE_DIR = "/opt/ml/model/faiss_indexes"

def preprocess_name_for_hash(name):
    """Preprocess urs_name for hashing, consistent with final_layout_parser.ipynb."""
    name = re.sub(r'^\d+\s*', '', name).strip()
    return re.sub(r'[^a-z0-9]', '', name.lower())

def get_faiss_index_path(urs_name):
    """Generate FAISS index path based on urs_name."""
    hashed_name = hashlib.md5(preprocess_name_for_hash(urs_name).encode()).hexdigest()
    return os.path.join(FAISS_BASE_DIR, f"{hashed_name}.index")

def model_fn(model_dir, context=None):
    """Load the SentenceTransformer model during endpoint initialization."""
    global sentence_model
    try:
        logger.info("Loading SentenceTransformer model")
        
        # Load SentenceTransformer model (static path remains unchanged)
        SENTENCE_MODEL_PATH = "/opt/ml/model/all-MiniLM-L6-v2"
        if not os.path.exists(SENTENCE_MODEL_PATH):
            raise FileNotFoundError(f"Model directory not found: {SENTENCE_MODEL_PATH}")
        sentence_model = SentenceTransformer(SENTENCE_MODEL_PATH, device=device)
        logger.info("SentenceTransformer model loaded successfully")

        # FAISS index will be loaded dynamically in predict_fn
        return {"sentence_model": sentence_model}
    except Exception as e:
        logger.error(f"Model loading failed: {str(e)}", exc_info=True)
        raise

def input_fn(request_body, request_content_type):
    """Parse the incoming request."""
    if request_content_type != "application/json":
        raise ValueError(f"Unsupported content type: {request_content_type}")
    
    try:
        if isinstance(request_body, bytes):
            request_body = request_body.decode("utf-8")
        data = json.loads(request_body)
        urs_name = data.get("urs_name")
        section_name = data.get("section_name")
        k = data.get("k", 5)

        if not urs_name or not section_name:
            logger.warning("Missing urs_name or section_name in request")
            raise ValueError("Missing urs_name or section_name")

        return {"urs_name": urs_name, "section_name": section_name, "k": k}
    except Exception as e:
        logger.error(f"Input parsing failed: {str(e)}", exc_info=True)
        raise

def predict_fn(input_data, model_dict):
    """Perform inference using the loaded model and dynamically loaded FAISS index."""
    try:
        logger.info(f"Processing query: urs_name={input_data['urs_name']}, section_name={input_data['section_name']}, k={input_data['k']}")
        sentence_model = model_dict["sentence_model"]

        # Dynamically load the FAISS index based on urs_name
        faiss_index_path = get_faiss_index_path(input_data["urs_name"])
        if not os.path.exists(faiss_index_path):
            logger.warning(f"FAISS index not found for urs_name={input_data['urs_name']} at {faiss_index_path}")
            raise FileNotFoundError(f"FAISS index not found: {faiss_index_path}")
        faiss_index = faiss.read_index(faiss_index_path)
        logger.info(f"Loaded FAISS index from {faiss_index_path}")

        # Construct query string
        separator = "|||"
        query_string = f"{input_data['urs_name']}{separator}{input_data['section_name']}{separator}content_type{separator}content"
        
        # Generate query embedding
        logger.debug("Generating query embedding")
        query_embedding = sentence_model.encode([query_string], convert_to_numpy=True)
        
        # Search FAISS index
        logger.debug("Searching FAISS index")
        distances, indices = faiss_index.search(query_embedding, input_data["k"])
        
        if indices.size == 0 or indices[0][0] == -1:
            logger.warning("No matching content found in FAISS index")
            raise ValueError("No matching content found")

        return {"indices": indices[0].tolist(), "distances": distances[0].tolist()}
    except Exception as e:
        logger.error(f"Prediction failed: {str(e)}", exc_info=True)
        raise

def output_fn(prediction, content_type):
    """Format the output for SageMaker."""
    if content_type != "application/json":
        raise ValueError(f"Unsupported content type: {content_type}")
    
    logger.info("Inference completed successfully")
    return json.dumps(prediction)