import torch
import boto3
from pathlib import Path
from sentence_transformers import SentenceTransformer
import faiss
from fastapi import FastAPI, HTTPException

# Initialize FastAPI app
app = FastAPI(title="FAISS Query API")

# Global variables
device = torch.device("cuda" if torch.cuda.is_available() else "cpu")
sentence_model = None
faiss_index = None
s3_client = boto3.client('s3')
BUCKET_NAME = "my-lifesciences-bucket"  # Replace with your S3 bucket name
FAISS_KEY = "models/faiss_index_retrained_batch_12.index"

# Initialize embedding tools (called once on startup)
@app.on_event("startup")
async def startup_event():
    global sentence_model, faiss_index
    if sentence_model is None:
        sentence_model = SentenceTransformer('all-MiniLM-L6-v2', device=device)
        print("SentenceTransformer model loaded")
    if faiss_index is None:
        local_path = "/tmp/faiss_index_retrained_batch_12.index"
        s3_client.download_file(BUCKET_NAME, FAISS_KEY, local_path)
        faiss_index = faiss.read_index(local_path)
        print("Loaded FAISS index from S3")

# Endpoint to query FAISS index
@app.get("/query_faiss/")
async def query_faiss(urs_name: str, section_name: str, k: int = 5):
    try:
        separator = "|||"
        query_string = f"{urs_name}{separator}{section_name}{separator}content_type{separator}content"
        query_embedding = sentence_model.encode([query_string], convert_to_numpy=True)
        
        # Search FAISS index
        distances, indices = faiss_index.search(query_embedding, k)
        if indices.size == 0 or indices[0][0] == -1:
            raise HTTPException(status_code=404, detail="No matching content found")
        
        # Return FAISS indices and distances
        return {"indices": indices[0].tolist(), "distances": distances[0].tolist()}
    
    except Exception as e:
        print(f"Query error: {e}")
        raise HTTPException(status_code=500, detail=str(e))

# SageMaker requires port 8080
if __name__ == "__main__":
    import uvicorn
    uvicorn.run(app, host="0.0.0.0", port=8080)