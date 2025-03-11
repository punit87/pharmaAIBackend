import os
import re
import numpy as np
import csv
from fastapi import FastAPI, Request
from sentence_transformers import SentenceTransformer
import faiss

# Constants
CSV_PATH = os.getenv('CSV_PATH', 'reference_file.csv')
FOLDER_PATH = os.getenv('FOLDER_PATH', './')
MODEL_REPO_ID = 'sentence-transformers/paraphrase-multilingual-mpnet-base-v2'
SIMILARITY_THRESHOLD = float(os.getenv('SIMILARITY_THRESHOLD', 0.4))

# Initialize embedding model
model = SentenceTransformer(MODEL_REPO_ID)

# Initialize FastAPI app
app = FastAPI()

# Smart chunking based on headings
def smart_chunking(text):
    chunks = []
    current_chunk = ""
    for line in text.split('\n'):
        if re.match(r'^\d+\.\s+.*', line):  # Matches headers like "6. Vessels"
            if current_chunk:
                chunks.append(current_chunk.strip())
            current_chunk = line
        else:
            current_chunk += ' ' + line
    if current_chunk:
        chunks.append(current_chunk.strip())
    return chunks

# Load text documents
def load_documents(folder_path):
    documents = []
    for filename in os.listdir(folder_path):
        if filename.endswith('.txt'):
            with open(os.path.join(folder_path, filename), 'r') as file:
                content = file.read()
                documents.extend(smart_chunking(content))  # Apply smart chunking
    print(f"Loaded {len(documents)} documents from text files.")
    return documents

# Load CSV data
def load_csv_data(csv_file):
    csv_text_data = []
    with open(csv_file, 'r') as file:
        reader = csv.reader(file)
        next(reader)  # Skip header
        for row in reader:
            csv_text_data.append(' '.join(row))  # Combine all columns into a single text
    print(f"Loaded {len(csv_text_data)} records from CSV.")
    return csv_text_data

# Prepare combined documents
def prepare_documents(folder_path, csv_file):
    text_documents = load_documents(folder_path)
    csv_data = load_csv_data(csv_file)
    combined = text_documents + csv_data
    print(f"Total combined documents: {len(combined)}")
    return combined

# Generate embeddings
def generate_embeddings(documents):
    print("Generating embeddings...")
    embeddings = model.encode(documents, normalize_embeddings=True, show_progress_bar=True)
    print(f"Generated embeddings for {len(documents)} documents.")
    return embeddings

# Build FAISS index with cosine similarity
def build_faiss_index(embeddings):
    dimension = embeddings.shape[1]
    index = faiss.IndexFlatIP(dimension)  # Inner Product for cosine similarity
    faiss.normalize_L2(embeddings)  # Normalize embeddings for cosine similarity
    index.add(embeddings)
    print(f"FAISS index built with {index.ntotal} vectors.")
    return index

# Encode query
def encode_query(query):
    return model.encode([query], normalize_embeddings=True).astype('float32')

# Search similar documents
def search_similar_documents(index, query, documents, k=10, threshold=SIMILARITY_THRESHOLD):
    query_embedding = encode_query(query)
    distances, indices = index.search(query_embedding, k)
    
    results = [documents[i] for i, d in zip(indices[0], distances[0]) if d > threshold]
    return results if results else ["No relevant documents found."]

# FastAPI Endpoint
@app.post("/query")
async def handle_query(request: Request):
    data = await request.json()
    query = data.get('inputs', '')
    results = search_similar_documents(faiss_index, query, combined_documents)
    combined_results = "\n".join(results)
    return [{"generated_text": combined_results}]

# Prepare documents and build index during startup
@app.on_event("startup")
async def startup_event():
    global combined_documents, faiss_index
    combined_documents = prepare_documents(FOLDER_PATH, CSV_PATH)
    embeddings = generate_embeddings(combined_documents)
    faiss_index = build_faiss_index(np.array(embeddings))
