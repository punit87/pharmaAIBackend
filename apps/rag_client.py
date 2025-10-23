#!/usr/bin/env python3
"""
RAG-Anything Server - Optimized for ECS Tasks
- Persistent event loop for efficient async operations
- Lazy initialization to reduce cold start time
- Proper resource cleanup
- Memory-efficient caching
"""
import os
import time
import json
import boto3
import asyncio
import threading
import atexit
from functools import lru_cache
from flask import Flask, request, jsonify
from raganything import RAGAnything, RAGAnythingConfig
from lightrag.llm.openai import openai_complete_if_cache, openai_embed
from lightrag.utils import EmbeddingFunc

app = Flask(__name__)

# Global state management
_event_loop = None
_rag_instance = None
_rag_lock = threading.Lock()

# ============================================================================
# EVENT LOOP MANAGEMENT (Persistent loop for all async operations)
# ============================================================================

def get_event_loop():
    """Get or create persistent event loop for async operations"""
    global _event_loop
    if _event_loop is None or _event_loop.is_closed():
        _event_loop = asyncio.new_event_loop()
        # Run loop in background thread
        loop_thread = threading.Thread(target=_event_loop.run_forever, daemon=True)
        loop_thread.start()
    return _event_loop

def run_async(coro):
    """Execute async coroutine in persistent event loop"""
    loop = get_event_loop()
    future = asyncio.run_coroutine_threadsafe(coro, loop)
    return future.result()

def cleanup_event_loop():
    """Cleanup event loop on shutdown"""
    global _event_loop
    if _event_loop and not _event_loop.is_closed():
        _event_loop.call_soon_threadsafe(_event_loop.stop)
        _event_loop.close()

atexit.register(cleanup_event_loop)

# ============================================================================
# ACTIVITY TRACKING (Simplified)
# ============================================================================

def update_activity():
    """Update activity timestamp for monitoring"""
    pass  # Simplified - no auto-stop logic

# ============================================================================
# RAG CONFIGURATION (Cached for reuse)
# ============================================================================

@lru_cache(maxsize=1)
def get_api_config():
    """Cache API configuration"""
    return {
        'api_key': os.environ.get('OPENAI_API_KEY'),
        'base_url': os.environ.get('OPENAI_BASE_URL'),
    }

@lru_cache(maxsize=1)
def get_rag_config():
    """Cache RAG configuration optimized for large documents"""
    return RAGAnythingConfig(
        working_dir=os.environ.get('OUTPUT_DIR', '/rag-output/'),
        parser=os.environ.get('PARSER', 'docling'),
        parse_method=os.environ.get('PARSE_METHOD', 'auto'),
        enable_image_processing=True,
        enable_table_processing=True,
        enable_equation_processing=True,
        # Large document handling optimizations
        chunk_size=int(os.environ.get('CHUNK_SIZE', '1000')),  # Smaller chunks for token limit
        chunk_overlap=int(os.environ.get('CHUNK_OVERLAP', '100')),  # Overlap between chunks
        max_context_length=int(os.environ.get('MAX_CONTEXT_LENGTH', '4000')),  # Reduced context length
        # Neo4j-specific optimizations
        # RAG-Anything will use the 1536-dimension embeddings for Neo4j vector indexes
        # This ensures compatibility with Neo4j's vector search capabilities
    )

def get_llm_model_func():
    """Create LLM model function with cached config"""
    config = get_api_config()
    
    def llm_func(prompt, system_prompt=None, history_messages=[], **kwargs):
        # Handle token limits for large prompts
        max_tokens = int(os.environ.get('MAX_TOKENS', '4000'))
        
        return openai_complete_if_cache(
            "gpt-4o-mini",
            prompt,
            system_prompt=system_prompt,
            history_messages=history_messages,
            api_key=config['api_key'],
            base_url=config['base_url'],
            max_tokens=max_tokens,
            **kwargs,
        )
    return llm_func

def get_vision_model_func(llm_func):
    """Create vision model function with cached config"""
    config = get_api_config()
    
    def vision_func(prompt, system_prompt=None, history_messages=[], 
                   image_data=None, messages=None, **kwargs):
        # Multimodal VLM enhanced query format
        if messages:
            return openai_complete_if_cache(
                "gpt-4o", "", system_prompt=None, history_messages=[],
                messages=messages, api_key=config['api_key'], 
                base_url=config['base_url'], **kwargs
            )
        # Single image format
        elif image_data:
            return openai_complete_if_cache(
                "gpt-4o", "", system_prompt=None, history_messages=[],
                messages=[
                    {"role": "system", "content": system_prompt} if system_prompt else None,
                    {
                        "role": "user",
                        "content": [
                            {"type": "text", "text": prompt},
                            {
                                "type": "image_url",
                                "image_url": {"url": f"data:image/jpeg;base64,{image_data}"}
                            }
                        ],
                    } if image_data else {"role": "user", "content": prompt}
                ],
                api_key=config['api_key'], base_url=config['base_url'], **kwargs
            )
        # Pure text fallback
        else:
            return llm_func(prompt, system_prompt, history_messages, **kwargs)
    
    return vision_func

def get_embedding_func():
    """
    Create embedding function optimized for Neo4j compatibility
    
    Using text-embedding-ada-002 for Neo4j compatibility:
    - Dimensions: 1536 (Neo4j standard)
    - Cost: $0.0001 per 1K tokens (most cost-effective)
    - Neo4j Support: Full compatibility with vector indexes
    - Rate Limits: Higher limits than newer models
    - Stability: Well-tested with Neo4j ecosystem
    """
    config = get_api_config()
    
    def safe_embed(texts):
        """Safe embedding function with error handling and retry logic"""
        try:
            return openai_embed(
                texts,
                model="text-embedding-ada-002",
                api_key=config['api_key'],
                base_url=config['base_url'],
            )
        except Exception as e:
            print(f"⚠️ [EMBEDDING] Error with text-embedding-ada-002: {e}")
            # For Neo4j compatibility, we stick with ada-002
            # If this fails, it's likely an API issue, not a model issue
            raise e
    
    return EmbeddingFunc(
        embedding_dim=1536,  # Neo4j-compatible dimensions
        max_token_size=8191,  # ada-002 token limit
        func=safe_embed,
    )

# ============================================================================
# LAZY RAG INITIALIZATION (Initialize once, reuse across requests)
# ============================================================================

def get_rag_instance():
    """Get or create singleton RAG instance (lazy initialization)"""
    global _rag_instance
    
    # Thread-safe singleton pattern
    if _rag_instance is None:
        with _rag_lock:
            if _rag_instance is None:
                print("🔧 [RAG] Initializing RAG-Anything singleton...")
                start = time.time()
                
                config = get_rag_config()
                llm_func = get_llm_model_func()
                vision_func = get_vision_model_func(llm_func)
                embedding_func = get_embedding_func()
                
                _rag_instance = RAGAnything(
                    config=config,
                    llm_model_func=llm_func,
                    vision_model_func=vision_func,
                    embedding_func=embedding_func,
                )
                
                print(f"✅ [RAG] Singleton initialized in {time.time()-start:.3f}s")
    
    return _rag_instance

# ============================================================================
# HEALTH CHECK
# ============================================================================

@app.route('/health', methods=['GET'])
def health():
    """Health check endpoint"""
    return jsonify({
        "status": "healthy",
        "service": "raganything",
        "uptime": 0,  # Simplified - no activity tracking
        "rag_initialized": _rag_instance is not None
    })

# ============================================================================
# DOCUMENT PROCESSING ENDPOINT
# ============================================================================

@app.route('/process', methods=['POST'])
def process_document():
    """Process document from S3 using RAG-Anything"""
    start_time = time.time()
    update_activity()
    
    print(f"\n{'='*60}")
    print(f"📄 [PROCESS] Starting at {time.strftime('%H:%M:%S')}")
    
    temp_file_path = None
    
    try:
        # Validate request
        data = request.get_json()
        s3_bucket = data.get('bucket')
        s3_key = data.get('key')
        
        if not s3_bucket or not s3_key:
            return jsonify({"error": "Missing bucket or key"}), 400
        
        print(f"📦 [PROCESS] Source: s3://{s3_bucket}/{s3_key}")
        
        # Step 1: Download from S3
        download_start = time.time()
        s3_client = boto3.client('s3')
        temp_file_path = f"/tmp/{os.path.basename(s3_key)}"
        s3_client.download_file(s3_bucket, s3_key, temp_file_path)
        download_duration = time.time() - download_start
        
        file_size = os.path.getsize(temp_file_path) / (1024 * 1024)  # MB
        print(f"📥 [PROCESS] Downloaded {file_size:.2f}MB in {download_duration:.3f}s")
        
        # Step 2: Get RAG instance (lazy init on first call)
        init_start = time.time()
        rag = get_rag_instance()
        init_duration = time.time() - init_start
        print(f"🚀 [PROCESS] RAG ready in {init_duration:.3f}s")
        
        # Step 3: Process document
        process_start = time.time()
        parser = os.environ.get('PARSER', 'docling')
        parse_method = os.environ.get('PARSE_METHOD', 'auto')
        
        process_kwargs = {
            'file_path': temp_file_path,
            'output_dir': os.environ.get('OUTPUT_DIR', '/rag-output/'),
            'doc_id': s3_key,
            'display_stats': True,
            'parse_method': parse_method,
        }
        
        # Add parser-specific parameters
        if parser == 'mineru':
            process_kwargs.update({
                'lang': os.environ.get('LANG', 'en'),
                'device': 'cpu',
                'formula': True,
                'table': True,
                'backend': 'pipeline',
                'source': 'local',
            })
        
        print(f"🔍 [PROCESS] Processing with {parser} parser ({parse_method} mode)")
        result = run_async(rag.process_document_complete(**process_kwargs))
        process_duration = time.time() - process_start
        
        print(f"💾 [PROCESS] Document processed in {process_duration:.3f}s")
        
        # Step 4: Cleanup
        if temp_file_path and os.path.exists(temp_file_path):
            os.remove(temp_file_path)
            print(f"🧹 [PROCESS] Temp file cleaned")
        
        total_duration = time.time() - start_time
        print(f"✅ [PROCESS] Total: {total_duration:.3f}s")
        print(f"{'='*60}\n")
        
        return jsonify({
            "status": "success",
            "result": result,
            "document": {
                "bucket": s3_bucket,
                "key": s3_key,
                "size_mb": round(file_size, 2)
            },
            "parser": {
                "type": parser,
                "method": parse_method
            },
            "timing": {
                "total_duration": round(total_duration, 3),
                "download_duration": round(download_duration, 3),
                "rag_init_duration": round(init_duration, 3),
                "process_duration": round(process_duration, 3)
            }
        })
        
    except Exception as e:
        total_duration = time.time() - start_time
        print(f"❌ [PROCESS] Error after {total_duration:.3f}s: {str(e)}")
        
        import traceback
        traceback.print_exc()
        
        # Cleanup on error
        if temp_file_path and os.path.exists(temp_file_path):
            try:
                os.remove(temp_file_path)
            except:
                pass
        
        return jsonify({
            "error": str(e),
            "timing": {"total_duration": round(total_duration, 3)}
        }), 500

# ============================================================================
# QUERY ENDPOINT
# ============================================================================

@app.route('/query', methods=['POST'])
def process_query():
    """Process RAG query"""
    start_time = time.time()
    update_activity()
    
    print(f"\n{'='*60}")
    print(f"🔍 [QUERY] Starting at {time.strftime('%H:%M:%S')}")
    
    try:
        # Validate request
        data = request.get_json()
        query = data.get('query', '')
        mode = data.get('mode', 'hybrid')
        vlm_enhanced = data.get('vlm_enhanced')
        
        if not query:
            return jsonify({"error": "Missing query"}), 400
        
        print(f"❓ [QUERY] Text: {query[:80]}{'...' if len(query) > 80 else ''}")
        print(f"⚙️ [QUERY] Mode: {mode}, VLM: {vlm_enhanced if vlm_enhanced is not None else 'auto'}")
        
        # Get RAG instance (reuses existing singleton)
        init_start = time.time()
        rag = get_rag_instance()
        init_duration = time.time() - init_start
        
        # Process query
        query_start = time.time()
        query_kwargs = {'mode': mode}
        if vlm_enhanced is not None:
            query_kwargs['vlm_enhanced'] = vlm_enhanced
        
        result = run_async(rag.aquery(query, **query_kwargs))
        query_duration = time.time() - query_start
        
        print(f"📊 [QUERY] Completed in {query_duration:.3f}s")
        
        # Parse result
        if isinstance(result, dict):
            answer = result.get('answer', str(result))
            sources = result.get('sources', [])
            confidence = result.get('confidence', 0.0)
        else:
            answer = str(result)
            sources = []
            confidence = 0.0
        
        total_duration = time.time() - start_time
        print(f"✅ [QUERY] Total: {total_duration:.3f}s")
        print(f"{'='*60}\n")
        
        return jsonify({
            "query": query,
            "answer": answer,
            "sources": sources,
            "confidence": confidence,
            "mode": mode,
            "vlm_enhanced": vlm_enhanced if vlm_enhanced is not None else "auto",
            "status": "completed",
            "timing": {
                "total_duration": round(total_duration, 3),
                "init_duration": round(init_duration, 3),
                "query_duration": round(query_duration, 3)
            }
        })
        
    except Exception as e:
        total_duration = time.time() - start_time
        print(f"❌ [QUERY] Error after {total_duration:.3f}s: {str(e)}")
        
        import traceback
        traceback.print_exc()
        
        return jsonify({
            "error": str(e),
            "query": query if 'query' in locals() else None,
            "answer": f"Error: {str(e)}",
            "sources": [],
            "confidence": 0.0,
            "status": "error",
            "timing": {"total_duration": round(total_duration, 3)}
        }), 500

# ============================================================================
# MULTIMODAL QUERY ENDPOINT
# ============================================================================

@app.route('/query_multimodal', methods=['POST'])
def process_multimodal_query():
    """Process multimodal RAG query with specific content (tables, equations, etc)"""
    start_time = time.time()
    update_activity()
    
    print(f"\n{'='*60}")
    print(f"🎨 [MULTIMODAL] Starting at {time.strftime('%H:%M:%S')}")
    
    try:
        # Validate request
        data = request.get_json()
        query = data.get('query', '')
        multimodal_content = data.get('multimodal_content', [])
        mode = data.get('mode', 'hybrid')
        
        if not query:
            return jsonify({"error": "Missing query"}), 400
        
        print(f"❓ [MULTIMODAL] Query: {query[:80]}{'...' if len(query) > 80 else ''}")
        print(f"🎨 [MULTIMODAL] Content items: {len(multimodal_content)}")
        
        # Get RAG instance
        init_start = time.time()
        rag = get_rag_instance()
        init_duration = time.time() - init_start
        
        # Process multimodal query
        query_start = time.time()
        result = run_async(rag.aquery_with_multimodal(
            query,
            multimodal_content=multimodal_content,
            mode=mode
        ))
        query_duration = time.time() - query_start
        
        print(f"📊 [MULTIMODAL] Completed in {query_duration:.3f}s")
        
        # Parse result
        if isinstance(result, dict):
            answer = result.get('answer', str(result))
            sources = result.get('sources', [])
            confidence = result.get('confidence', 0.0)
        else:
            answer = str(result)
            sources = []
            confidence = 0.0
        
        total_duration = time.time() - start_time
        print(f"✅ [MULTIMODAL] Total: {total_duration:.3f}s")
        print(f"{'='*60}\n")
        
        return jsonify({
            "query": query,
            "answer": answer,
            "sources": sources,
            "confidence": confidence,
            "mode": mode,
            "multimodal_items": len(multimodal_content),
            "status": "completed",
            "timing": {
                "total_duration": round(total_duration, 3),
                "init_duration": round(init_duration, 3),
                "query_duration": round(query_duration, 3)
            }
        })
        
    except Exception as e:
        total_duration = time.time() - start_time
        print(f"❌ [MULTIMODAL] Error after {total_duration:.3f}s: {str(e)}")
        
        import traceback
        traceback.print_exc()
        
        return jsonify({
            "error": str(e),
            "query": query if 'query' in locals() else None,
            "answer": f"Error: {str(e)}",
            "sources": [],
            "confidence": 0.0,
            "status": "error",
            "timing": {"total_duration": round(total_duration, 3)}
        }), 500

@app.route('/analyze_efs', methods=['GET'])
def analyze_efs():
    """Analyze EFS contents - chunks, embeddings, metadata, graphs"""
    try:
        efs_path = os.environ.get('EFS_MOUNT_PATH', '/mnt/efs')
        rag_output_dir = os.environ.get('RAG_OUTPUT_DIR', '/mnt/efs/rag_output')
        
        analysis = {
            'efs_path': efs_path,
            'rag_output_dir': rag_output_dir,
            'efs_exists': os.path.exists(efs_path),
            'rag_output_exists': os.path.exists(rag_output_dir),
            'files': [],
            'chunks': [],
            'embeddings': [],
            'metadata': [],
            'graphs': [],
            'total_files': 0,
            'total_size_bytes': 0
        }
        
        if not os.path.exists(efs_path):
            return jsonify({
                'error': f'EFS path {efs_path} not found',
                'analysis': analysis
            }), 404
        
        # Walk through EFS directory and collect file information
        for root, dirs, files in os.walk(efs_path):
            for file in files:
                file_path = os.path.join(root, file)
                try:
                    file_size = os.path.getsize(file_path)
                    relative_path = os.path.relpath(file_path, efs_path)
                    
                    file_info = {
                        'path': file_path,
                        'relative_path': relative_path,
                        'name': file,
                        'size_bytes': file_size,
                        'directory': root
                    }
                    
                    analysis['files'].append(file_info)
                    analysis['total_files'] += 1
                    analysis['total_size_bytes'] += file_size
                    
                    # Categorize files by type
                    if file.endswith('.json'):
                        if 'chunk' in file.lower() or 'chunks' in root.lower():
                            analysis['chunks'].append(file_info)
                        elif 'embedding' in file.lower() or 'embeddings' in root.lower():
                            analysis['embeddings'].append(file_info)
                        elif 'metadata' in file.lower() or 'meta' in file.lower():
                            analysis['metadata'].append(file_info)
                        elif 'graph' in file.lower() or 'neo4j' in file.lower():
                            analysis['graphs'].append(file_info)
                    
                except Exception as e:
                    analysis['files'].append({
                        'path': file_path,
                        'name': file,
                        'error': str(e)
                    })
        
        # Try to read some sample chunk files to show content
        sample_chunks = []
        for chunk_file in analysis['chunks'][:5]:  # First 5 chunk files
            try:
                with open(chunk_file['path'], 'r', encoding='utf-8') as f:
                    chunk_data = json.load(f)
                    sample_chunks.append({
                        'file': chunk_file['relative_path'],
                        'content_preview': str(chunk_data)[:200] + '...' if len(str(chunk_data)) > 200 else str(chunk_data)
                    })
            except Exception as e:
                sample_chunks.append({
                    'file': chunk_file['relative_path'],
                    'error': str(e)
                })
        
        analysis['sample_chunks'] = sample_chunks
        
        # Try to read some sample metadata files
        sample_metadata = []
        for meta_file in analysis['metadata'][:3]:  # First 3 metadata files
            try:
                with open(meta_file['path'], 'r', encoding='utf-8') as f:
                    meta_data = json.load(f)
                    sample_metadata.append({
                        'file': meta_file['relative_path'],
                        'content_preview': str(meta_data)[:200] + '...' if len(str(meta_data)) > 200 else str(meta_data)
                    })
            except Exception as e:
                sample_metadata.append({
                    'file': meta_file['relative_path'],
                    'error': str(e)
                })
        
        analysis['sample_metadata'] = sample_metadata
        
        return jsonify({
            'status': 'success',
            'analysis': analysis
        })
        
    except Exception as e:
        return jsonify({
            'error': str(e),
            'status': 'error'
        }), 500

# ============================================================================
# SERVER STARTUP
# ============================================================================

def start_server():
    """Start the Flask server"""
    port = int(os.environ.get('PORT', 8000))
    
    print("\n" + "="*60)
    print("🚀 RAG-Anything Server")
    print("="*60)
    print(f"📍 Port: {port}")
    print(f"📂 Working Dir: {os.environ.get('OUTPUT_DIR', '/rag-output/')}")
    print(f"🔧 Parser: {os.environ.get('PARSER', 'docling')}")
    print(f"📝 Parse Method: {os.environ.get('PARSE_METHOD', 'auto')}")
    print(f"🔄 Lazy Init: RAG instance created on first request")
    print("="*60 + "\n")
    
    # Use threaded mode for better request handling
    app.run(
        host='0.0.0.0',
        port=port,
        debug=False,
        threaded=True,
        use_reloader=False
    )

if __name__ == '__main__':
    start_server()