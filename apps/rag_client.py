#!/usr/bin/env python3
"""
RAG-Anything Server - Proper implementation following official API
Based on https://github.com/HKUDS/RAG-Anything
"""
import os
import time
import boto3
import asyncio
import threading
from typing import Dict, Any
from flask import Flask, request, jsonify
from raganything import RAGAnything, RAGAnythingConfig
from lightrag.llm.openai import openai_complete_if_cache, openai_embed
from lightrag.utils import EmbeddingFunc

app = Flask(__name__)

# Auto-stop configuration
IDLE_TIMEOUT = 600  # 10 minutes in seconds
last_activity = time.time()
shutdown_flag = threading.Event()

def auto_stop_timer():
    """Background thread to check for inactivity and stop the container"""
    global last_activity
    
    while not shutdown_flag.is_set():
        current_time = time.time()
        if current_time - last_activity > IDLE_TIMEOUT:
            print(f"Container idle for {IDLE_TIMEOUT} seconds. Shutting down...")
            os._exit(0)
        time.sleep(30)  # Check every 30 seconds

def update_activity():
    """Update the last activity timestamp"""
    global last_activity
    last_activity = time.time()

def get_rag_config():
    """Create RAGAnything configuration from environment variables"""
    return RAGAnythingConfig(
        working_dir=os.environ.get('OUTPUT_DIR', '/rag-output/'),
        parser=os.environ.get('PARSER', 'docling'),  # 'mineru' or 'docling'
        parse_method=os.environ.get('PARSE_METHOD', 'auto'),  # 'auto', 'ocr', or 'txt'
        enable_image_processing=True,
        enable_table_processing=True,
        enable_equation_processing=True,
    )

def get_llm_model_func():
    """Create LLM model function for text processing"""
    api_key = os.environ.get('OPENAI_API_KEY')
    base_url = os.environ.get('OPENAI_BASE_URL')
    
    def llm_func(prompt, system_prompt=None, history_messages=[], **kwargs):
        return openai_complete_if_cache(
            "gpt-4o-mini",
            prompt,
            system_prompt=system_prompt,
            history_messages=history_messages,
            api_key=api_key
            **kwargs,
        )
    return llm_func

def get_vision_model_func(llm_func):
    """Create vision model function for image processing"""
    api_key = os.environ.get('OPENAI_API_KEY')
    base_url = os.environ.get('OPENAI_BASE_URL')
    
    def vision_func(prompt, system_prompt=None, history_messages=[], image_data=None, messages=None, **kwargs):
        # If messages format is provided (for multimodal VLM enhanced query), use it directly
        if messages:
            return openai_complete_if_cache(
                "gpt-4o",
                "",
                system_prompt=None,
                history_messages=[],
                messages=messages,
                api_key=api_key,
                base_url=base_url,
                **kwargs,
            )
        # Traditional single image format
        elif image_data:
            return openai_complete_if_cache(
                "gpt-4o",
                "",
                system_prompt=None,
                history_messages=[],
                messages=[
                    {"role": "system", "content": system_prompt} if system_prompt else None,
                    {
                        "role": "user",
                        "content": [
                            {"type": "text", "text": prompt},
                            {
                                "type": "image_url",
                                "image_url": {"url": f"data:image/jpeg;base64,{image_data}"}
                            },
                        ],
                    } if image_data else {"role": "user", "content": prompt},
                ],
                api_key=api_key,
                base_url=base_url,
                **kwargs,
            )
        # Pure text format - fallback to LLM
        else:
            return llm_func(prompt, system_prompt, history_messages, **kwargs)
    
    return vision_func

def get_embedding_func():
    """Create embedding function"""
    api_key = os.environ.get('OPENAI_API_KEY')
    base_url = os.environ.get('OPENAI_BASE_URL')
    
    return EmbeddingFunc(
        embedding_dim=3072,
        max_token_size=8192,
        func=lambda texts: openai_embed(
            texts,
            model="text-embedding-3-large",
            api_key=api_key,
            base_url=base_url,
        ),
    )

def initialize_rag_anything():
    """Initialize RAG-Anything with proper configuration"""
    config = get_rag_config()
    llm_func = get_llm_model_func()
    vision_func = get_vision_model_func(llm_func)
    embedding_func = get_embedding_func()
    
    return RAGAnything(
        config=config,
        llm_model_func=llm_func,
        vision_model_func=vision_func,
        embedding_func=embedding_func,
    )

# Start the auto-stop timer
timer_thread = threading.Thread(target=auto_stop_timer, daemon=True)
timer_thread.start()

@app.route('/health', methods=['GET'])
def health():
    """Health check endpoint"""
    return jsonify({"status": "healthy", "service": "raganything"})

@app.route('/process', methods=['POST'])
async def process_document():
    """Process document using RAG-Anything with proper async handling"""
    start_time = time.time()
    print(f"📄 [RAG] Starting document processing at {time.strftime('%Y-%m-%d %H:%M:%S')}")
    
    try:
        update_activity()
        
        data = request.get_json()
        s3_bucket = data.get('bucket')
        s3_key = data.get('key')
        
        if not s3_bucket or not s3_key:
            duration = time.time() - start_time
            print(f"❌ [RAG] Missing bucket or key - {duration:.3f}s")
            return jsonify({"error": "Missing bucket or key"}), 400
        
        print(f"📄 [RAG] Processing document: s3://{s3_bucket}/{s3_key}")
        
        # Download file from S3
        download_start = time.time()
        s3_client = boto3.client('s3')
        temp_file_path = f"/tmp/{os.path.basename(s3_key)}"
        s3_client.download_file(s3_bucket, s3_key, temp_file_path)
        download_duration = time.time() - download_start
        print(f"📥 [RAG] S3 download completed in {download_duration:.3f}s")
        
        # Initialize RAG-Anything
        init_start = time.time()
        rag = initialize_rag_anything()
        init_duration = time.time() - init_start
        print(f"🚀 [RAG] RAG-Anything initialization completed in {init_duration:.3f}s")
        
        # Process document using RAG-Anything
        process_start = time.time()
        print(f"🔍 [RAG] Processing document with RAG-Anything")
        
        # Get parser-specific parameters
        parser = os.environ.get('PARSER', 'docling')
        parse_method = os.environ.get('PARSE_METHOD', 'auto')
        
        # Build kwargs based on parser
        process_kwargs = {
            'file_path': temp_file_path,
            'output_dir': os.environ.get('OUTPUT_DIR', '/rag-output/'),
            'doc_id': s3_key,
            'display_stats': True,
            'parse_method': parse_method,
        }
        
        # Add MinerU-specific parameters if using MinerU parser
        if parser == 'mineru':
            process_kwargs.update({
                'lang': 'en',
                'device': 'cpu',
                'formula': True,
                'table': True,
                'backend': 'pipeline',
                'source': 'local',
            })
        
        # Process document
        result = await rag.process_document_complete(**process_kwargs)
        
        process_duration = time.time() - process_start
        print(f"💾 [RAG] Document processing completed in {process_duration:.3f}s")
        
        # Clean up temp file
        cleanup_start = time.time()
        os.remove(temp_file_path)
        cleanup_duration = time.time() - cleanup_start
        print(f"🧹 [RAG] Cleanup completed in {cleanup_duration:.3f}s")
        
        total_duration = time.time() - start_time
        print(f"✅ [RAG] Total processing time: {total_duration:.3f}s")
        
        return jsonify({
            "status": "success",
            "result": result,
            "message": f"Document processed successfully with RAG-Anything + {parser} parser",
            "timing": {
                "total_duration": total_duration,
                "download_duration": download_duration,
                "rag_init_duration": init_duration,
                "rag_process_duration": process_duration,
                "cleanup_duration": cleanup_duration
            }
        })
        
    except Exception as e:
        total_duration = time.time() - start_time
        print(f"❌ [RAG] Error processing document: {str(e)} - {total_duration:.3f}s")
        import traceback
        traceback.print_exc()
        return jsonify({"error": str(e), "timing": {"total_duration": total_duration}}), 500

@app.route('/query', methods=['POST'])
async def process_query():
    """Process RAG query using RAG-Anything with proper async handling"""
    start_time = time.time()
    print(f"🔍 [RAG] Starting query processing at {time.strftime('%Y-%m-%d %H:%M:%S')}")
    
    try:
        update_activity()
        
        data = request.get_json()
        query = data.get('query', '')
        mode = data.get('mode', 'hybrid')  # hybrid, local, global, naive
        vlm_enhanced = data.get('vlm_enhanced', None)  # None = auto, True/False = force
        
        if not query:
            duration = time.time() - start_time
            print(f"❌ [RAG] Missing query - {duration:.3f}s")
            return jsonify({"error": "Missing query"}), 400
        
        print(f"❓ [RAG] Processing query: {query[:100]}{'...' if len(query) > 100 else ''}")
        
        # Initialize RAG-Anything
        init_start = time.time()
        rag = initialize_rag_anything()
        init_duration = time.time() - init_start
        print(f"🚀 [RAG] RAG-Anything initialization completed in {init_duration:.3f}s")
        
        # Process query
        query_start = time.time()
        
        # Build query kwargs
        query_kwargs = {'mode': mode}
        if vlm_enhanced is not None:
            query_kwargs['vlm_enhanced'] = vlm_enhanced
        
        # Use async query method
        result = await rag.aquery(query, **query_kwargs)
        
        query_duration = time.time() - query_start
        print(f"📊 [RAG] Query processing completed in {query_duration:.3f}s")
        
        total_duration = time.time() - start_time
        print(f"✅ [RAG] Total query time: {total_duration:.3f}s")
        
        # Handle different result formats
        if isinstance(result, dict):
            answer = result.get('answer', str(result))
            sources = result.get('sources', [])
            confidence = result.get('confidence', 0.0)
        else:
            answer = str(result)
            sources = []
            confidence = 0.0
        
        return jsonify({
            "query": query,
            "answer": answer,
            "sources": sources,
            "confidence": confidence,
            "mode": mode,
            "status": "completed",
            "timing": {
                "total_duration": total_duration,
                "init_duration": init_duration,
                "query_duration": query_duration
            }
        })
        
    except Exception as e:
        total_duration = time.time() - start_time
        print(f"❌ [RAG] Error processing query: {str(e)} - {total_duration:.3f}s")
        import traceback
        traceback.print_exc()
        return jsonify({
            "error": str(e),
            "query": query if 'query' in locals() else None,
            "answer": f"Error processing query: {str(e)}",
            "sources": [],
            "confidence": 0.0,
            "status": "error",
            "timing": {"total_duration": total_duration}
        }), 500

@app.route('/query_multimodal', methods=['POST'])
async def process_multimodal_query():
    """Process multimodal RAG query with specific content types"""
    start_time = time.time()
    print(f"🔍 [RAG] Starting multimodal query processing at {time.strftime('%Y-%m-%d %H:%M:%S')}")
    
    try:
        update_activity()
        
        data = request.get_json()
        query = data.get('query', '')
        multimodal_content = data.get('multimodal_content', [])
        mode = data.get('mode', 'hybrid')
        
        if not query:
            duration = time.time() - start_time
            print(f"❌ [RAG] Missing query - {duration:.3f}s")
            return jsonify({"error": "Missing query"}), 400
        
        print(f"❓ [RAG] Processing multimodal query: {query[:100]}{'...' if len(query) > 100 else ''}")
        
        # Initialize RAG-Anything
        init_start = time.time()
        rag = initialize_rag_anything()
        init_duration = time.time() - init_start
        print(f"🚀 [RAG] RAG-Anything initialization completed in {init_duration:.3f}s")
        
        # Process multimodal query
        query_start = time.time()
        result = await rag.aquery_with_multimodal(
            query,
            multimodal_content=multimodal_content,
            mode=mode
        )
        query_duration = time.time() - query_start
        print(f"📊 [RAG] Multimodal query processing completed in {query_duration:.3f}s")
        
        total_duration = time.time() - start_time
        print(f"✅ [RAG] Total multimodal query time: {total_duration:.3f}s")
        
        # Handle different result formats
        if isinstance(result, dict):
            answer = result.get('answer', str(result))
            sources = result.get('sources', [])
            confidence = result.get('confidence', 0.0)
        else:
            answer = str(result)
            sources = []
            confidence = 0.0
        
        return jsonify({
            "query": query,
            "answer": answer,
            "sources": sources,
            "confidence": confidence,
            "mode": mode,
            "status": "completed",
            "timing": {
                "total_duration": total_duration,
                "init_duration": init_duration,
                "query_duration": query_duration
            }
        })
        
    except Exception as e:
        total_duration = time.time() - start_time
        print(f"❌ [RAG] Error processing multimodal query: {str(e)} - {total_duration:.3f}s")
        import traceback
        traceback.print_exc()
        return jsonify({
            "error": str(e),
            "query": query if 'query' in locals() else None,
            "answer": f"Error processing query: {str(e)}",
            "sources": [],
            "confidence": 0.0,
            "status": "error",
            "timing": {"total_duration": total_duration}
        }), 500

if __name__ == '__main__':
    # Run Flask server with async support
    from asgiref.wsgi import WsgiToAsgi
    from hypercorn.asyncio import serve
    from hypercorn.config import Config
    
    port = int(os.environ.get('PORT', 8000))
    print(f"🚀 [RAG] Starting RAG-Anything async server on port {port}")
    
    # Convert WSGI to ASGI for proper async support
    asgi_app = WsgiToAsgi(app)
    config = Config()
    config.bind = [f"0.0.0.0:{port}"]
    
    asyncio.run(serve(asgi_app, config))