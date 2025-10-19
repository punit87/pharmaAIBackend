from fastapi import FastAPI, HTTPException
from pydantic import BaseModel
import os
from raganything import RAGAnything, RAGAnythingConfig
from lightrag.llm.openai import openai_complete_if_cache, openai_embed
from lightrag.utils import EmbeddingFunc

app = FastAPI(title="RAG-Anything API", version="1.0.0")

# Global RAG instance
rag_instance = None

class QueryRequest(BaseModel):
    query: str
    document: str = None

class QueryResponse(BaseModel):
    query: str
    answer: str
    status: str

def get_rag_instance():
    """Initialize RAG instance if not already done"""
    global rag_instance
    if rag_instance is None:
        # Initialize RAG-Anything
        config = RAGAnythingConfig(
            working_dir="/tmp/rag_storage",
            enable_image_processing=True,
            enable_table_processing=True,
            enable_equation_processing=True,
        )
        
        # Set up LLM functions
        def llm_model_func(prompt, system_prompt=None, history_messages=[], **kwargs):
            return openai_complete_if_cache(
                "gpt-4o-mini",
                prompt,
                system_prompt=system_prompt,
                history_messages=history_messages,
                api_key=os.environ.get('OPENAI_API_KEY'),
                **kwargs,
            )
        
        embedding_func = EmbeddingFunc(
            embedding_dim=3072,
            max_token_size=8192,
            func=lambda texts: openai_embed(
                texts,
                model="text-embedding-3-large",
                api_key=os.environ.get('OPENAI_API_KEY'),
            ),
        )
        
        rag_instance = RAGAnything(
            config=config,
            llm_model_func=llm_model_func,
            embedding_func=embedding_func,
        )
    
    return rag_instance

@app.get("/health")
async def health_check():
    """Health check endpoint for Fargate"""
    return {"status": "healthy", "service": "rag-anything"}

@app.post("/query", response_model=QueryResponse)
async def query_rag(request: QueryRequest):
    """Query the RAG system"""
    try:
        rag = get_rag_instance()
        
        # Process document if provided
        if request.document:
            # This would need to be implemented based on your document processing needs
            pass
        
        # Query the RAG system
        result = rag.query(request.query, mode="hybrid")
        
        return QueryResponse(
            query=request.query,
            answer=result,
            status="success"
        )
        
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))

@app.get("/")
async def root():
    """Root endpoint"""
    return {"message": "RAG-Anything API is running", "version": "1.0.0"}

if __name__ == "__main__":
    import uvicorn
    uvicorn.run(app, host="0.0.0.0", port=8080)
