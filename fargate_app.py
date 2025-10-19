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

class DocumentRequest(BaseModel):
    document: str
    document_type: str = "url"  # "url" or "base64"

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
            try:
                # Handle different document types
                if request.document.startswith('http'):
                    # Download document from URL
                    import requests
                    response = requests.get(request.document)
                    if response.status_code == 200:
                        # Save to temporary file
                        import tempfile
                        with tempfile.NamedTemporaryFile(delete=False, suffix='.pdf') as tmp_file:
                            tmp_file.write(response.content)
                            document_path = tmp_file.name
                    else:
                        raise HTTPException(status_code=400, detail="Failed to download document from URL")
                else:
                    # Assume document is base64 encoded content
                    import base64
                    import tempfile
                    try:
                        # Decode base64 content
                        document_content = base64.b64decode(request.document)
                        # Save to temporary file
                        with tempfile.NamedTemporaryFile(delete=False, suffix='.pdf') as tmp_file:
                            tmp_file.write(document_content)
                            document_path = tmp_file.name
                    except Exception as e:
                        raise HTTPException(status_code=400, detail=f"Invalid document format: {str(e)}")
                
                # Process document with RAG-Anything
                print(f"Processing document: {document_path}")
                
                # Use RAG-Anything to process the document
                # This will create embeddings and store them in the working directory
                rag.insert(document_path)
                
                # Clean up temporary file
                import os
                os.unlink(document_path)
                
                print("Document processed successfully")
                
            except Exception as e:
                print(f"Error processing document: {str(e)}")
                raise HTTPException(status_code=500, detail=f"Document processing failed: {str(e)}")
        
        # Query the RAG system
        result = rag.query(request.query, mode="hybrid")
        
        return QueryResponse(
            query=request.query,
            answer=result,
            status="success"
        )
        
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))

@app.post("/process-document")
async def process_document(request: DocumentRequest):
    """Process a document and add it to the RAG system"""
    try:
        rag = get_rag_instance()
        
        # Handle different document types
        if request.document_type == "url":
            # Download document from URL
            import requests
            response = requests.get(request.document)
            if response.status_code == 200:
                # Save to temporary file
                import tempfile
                with tempfile.NamedTemporaryFile(delete=False, suffix='.pdf') as tmp_file:
                    tmp_file.write(response.content)
                    document_path = tmp_file.name
            else:
                raise HTTPException(status_code=400, detail="Failed to download document from URL")
        else:
            # Assume document is base64 encoded content
            import base64
            import tempfile
            try:
                # Decode base64 content
                document_content = base64.b64decode(request.document)
                # Save to temporary file
                with tempfile.NamedTemporaryFile(delete=False, suffix='.pdf') as tmp_file:
                    tmp_file.write(document_content)
                    document_path = tmp_file.name
            except Exception as e:
                raise HTTPException(status_code=400, detail=f"Invalid document format: {str(e)}")
        
        # Process document with RAG-Anything
        print(f"Processing document: {document_path}")
        
        # Use RAG-Anything to process the document
        # This will create embeddings and store them in the working directory
        rag.insert(document_path)
        
        # Clean up temporary file
        import os
        os.unlink(document_path)
        
        print("Document processed successfully")
        
        return {
            "status": "success",
            "message": "Document processed and added to RAG system",
            "document_type": request.document_type
        }
        
    except Exception as e:
        print(f"Error processing document: {str(e)}")
        raise HTTPException(status_code=500, detail=f"Document processing failed: {str(e)}")

@app.get("/")
async def root():
    """Root endpoint"""
    return {"message": "RAG-Anything API is running", "version": "1.0.0"}

if __name__ == "__main__":
    import uvicorn
    uvicorn.run(app, host="0.0.0.0", port=8080)
