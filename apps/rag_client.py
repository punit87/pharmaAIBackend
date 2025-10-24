#!/usr/bin/env python3
"""
RAG-Anything Server - Optimized for ECS Tasks
- Persistent event loop for efficient async operations
- Lazy initialization to reduce cold start time
- Proper resource cleanup
- Memory-efficient caching
- Fixed async handling matching RAG-Anything reference implementation
"""
import os
import time
import json
import boto3
import asyncio
import threading
import atexit
import logging
from functools import lru_cache
from flask import Flask, request, jsonify
from raganything import RAGAnything, RAGAnythingConfig
from lightrag.llm.openai import openai_complete_if_cache, openai_embed
from lightrag.utils import EmbeddingFunc

# Configure logging
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s',
    handlers=[
        logging.StreamHandler(),
        logging.FileHandler('/tmp/rag_client.log')
    ]
)
logger = logging.getLogger(__name__)

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
    start_time = time.time()
    logger.info("🔄 [EVENT_LOOP] Getting event loop...")
    
    if _event_loop is None or _event_loop.is_closed():
        logger.info("🔄 [EVENT_LOOP] Creating new event loop...")
        _event_loop = asyncio.new_event_loop()
        # Run loop in background thread
        loop_thread = threading.Thread(target=_event_loop.run_forever, daemon=True)
        loop_thread.start()
        logger.info(f"🔄 [EVENT_LOOP] Event loop created and started in {time.time() - start_time:.3f}s")
    else:
        logger.info(f"🔄 [EVENT_LOOP] Using existing event loop in {time.time() - start_time:.3f}s")
    
    return _event_loop

def run_async(coro):
    """Execute async coroutine in persistent event loop"""
    start_time = time.time()
    logger.info("🔄 [ASYNC] Executing async coroutine...")
    
    try:
        loop = get_event_loop()
        future = asyncio.run_coroutine_threadsafe(coro, loop)
        result = future.result(timeout=300)  # 5 minute timeout
        
        logger.info(f"🔄 [ASYNC] Async coroutine completed in {time.time() - start_time:.3f}s")
        return result
    except Exception as e:
        logger.error(f"❌ [ASYNC] Async coroutine failed after {time.time() - start_time:.3f}s: {str(e)}")
        raise e

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
    start_time = time.time()
    logger.info("⚙️ [CONFIG] Getting RAG configuration...")
    
    config = RAGAnythingConfig(
        working_dir=os.environ.get('OUTPUT_DIR', '/rag-output/'),
        parser=os.environ.get('PARSER', 'docling'),
        parse_method=os.environ.get('PARSE_METHOD', 'ocr'),
        enable_image_processing=True,
        enable_table_processing=True,
        enable_equation_processing=True
    )
    
    logger.info(f"⚙️ [CONFIG] RAG configuration loaded in {time.time() - start_time:.3f}s")
    logger.info(f"⚙️ [CONFIG] Working dir: {config.working_dir}")
    logger.info(f"⚙️ [CONFIG] Parser: {config.parser}")
    logger.info(f"⚙️ [CONFIG] Parse method: {config.parse_method}")
    logger.info(f"⚙️ [CONFIG] Image processing: {config.enable_image_processing}")
    logger.info(f"⚙️ [CONFIG] Table processing: {config.enable_table_processing}")
    logger.info(f"⚙️ [CONFIG] Equation processing: {config.enable_equation_processing}")
    
    return config

def get_llm_model_func():
    """
    Create LLM model function - SYNCHRONOUS wrapper that returns coroutine
    This matches the RAG-Anything reference implementation
    """
    start_time = time.time()
    logger.info("🤖 [LLM] Creating LLM model function...")
    
    config = get_api_config()
    
    def llm_func(prompt, system_prompt=None, history_messages=[], **kwargs):
        """
        Synchronous function that returns a coroutine
        RAG-Anything will handle the async execution internally
        """
        llm_start_time = time.time()
        logger.info(f"🤖 [LLM] Starting LLM completion...")
        logger.info(f"🤖 [LLM] Prompt length: {len(prompt)} characters")
        
        max_tokens = int(os.environ.get('MAX_TOKENS', '4000'))
        
        # Return the coroutine directly - RAG-Anything handles await
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
    
    logger.info(f"🤖 [LLM] LLM model function created in {time.time() - start_time:.3f}s")
    return llm_func

def get_vision_model_func(llm_func):
    """
    Create vision model function - SYNCHRONOUS wrapper that returns coroutine
    This matches the RAG-Anything reference implementation
    """
    config = get_api_config()
    
    def vision_func(prompt, system_prompt=None, history_messages=[], 
                   image_data=None, messages=None, **kwargs):
        """
        Synchronous function that returns a coroutine
        RAG-Anything will handle the async execution internally
        """
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
    Create embedding function - SYNCHRONOUS wrapper that returns coroutine
    This matches the RAG-Anything reference implementation
    
    Using text-embedding-ada-002 for Neo4j compatibility:
    - Dimensions: 1536 (Neo4j standard)
    - Cost: $0.0001 per 1K tokens (most cost-effective)
    - Neo4j Support: Full compatibility with vector indexes
    """
    config = get_api_config()
    
    def safe_embed(texts):
        """
        Synchronous function that returns a coroutine
        RAG-Anything will handle the async execution internally
        """
        try:
            # Return the coroutine directly - RAG-Anything handles await
            return openai_embed(
                texts,
                model="text-embedding-ada-002",
                api_key=config['api_key'],
                base_url=config['base_url'],
            )
        except Exception as e:
            logger.error(f"⚠️ [EMBEDDING] Error: {e}")
            raise e
    
    return EmbeddingFunc(
        embedding_dim=1536,  # Neo4j-compatible dimensions
        max_token_size=8191,  # ada-002 token limit
        func=safe_embed,
    )

# ============================================================================
# LAZY RAG INITIALIZATION
# ============================================================================

def get_rag_instance():
    """Get or create singleton RAG instance"""
    global _rag_instance
    start_time = time.time()
    logger.info("🚀 [RAG_INIT] Getting RAG instance...")
    
    if _rag_instance is None:
        with _rag_lock:
            if _rag_instance is None:
                logger.info("🚀 [RAG_INIT] Creating new RAG-Anything singleton...")
                
                try:
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
                    
                    logger.info(f"🚀 [RAG_INIT] Initialized in {time.time()-start_time:.3f}s")
                    
                except Exception as e:
                    logger.error(f"🚀 [RAG_INIT] Failed: {str(e)}")
                    raise
    
    return _rag_instance

# ============================================================================
# HEALTH CHECK
# ============================================================================

@app.route('/health', methods=['GET'])
def health():
    """Health check endpoint"""
    try:
        rag_instance = get_rag_instance()
        return jsonify({
            "status": "healthy",
            "service": "raganything",
            "rag_initialized": rag_instance is not None
        })
    except Exception as e:
        return jsonify({
            "status": "unhealthy",
            "error": str(e)
        }), 500

# ============================================================================
# DOCUMENT PROCESSING
# ============================================================================

@app.route('/process', methods=['POST'])
def process_document():
    """Process document from S3"""
    start_time = time.time()
    logger.info("📄 [PROCESS] Document processing started...")
    temp_file_path = None
    
    try:
        data = request.get_json()
        s3_bucket = data.get('bucket')
        s3_key = data.get('key')
        
        if not s3_bucket or not s3_key:
            return jsonify({"error": "Missing bucket or key"}), 400
        
        logger.info(f"📦 [PROCESS] s3://{s3_bucket}/{s3_key}")
        
        # Download from S3
        download_start = time.time()
        s3_client = boto3.client('s3')
        temp_file_path = f"/tmp/{os.path.basename(s3_key)}"
        s3_client.download_file(s3_bucket, s3_key, temp_file_path)
        download_duration = time.time() - download_start
        file_size = os.path.getsize(temp_file_path) / (1024 * 1024)
        logger.info(f"📥 [PROCESS] Downloaded {file_size:.2f}MB in {download_duration:.3f}s")
        
        # Get RAG instance
        init_start = time.time()
        rag = get_rag_instance()
        init_duration = time.time() - init_start
        
        # Process document
        process_start = time.time()
        parser = os.environ.get('PARSER', 'docling')
        parse_method = os.environ.get('PARSE_METHOD', 'ocr')
        
        process_kwargs = {
            'file_path': temp_file_path,
            'output_dir': os.environ.get('OUTPUT_DIR', '/rag-output/'),
            'doc_id': s3_key,
            'display_stats': True,
            'parse_method': parse_method,
        }
        
        if parser == 'mineru':
            process_kwargs.update({
                'lang': os.environ.get('LANG', 'en'),
                'device': 'cpu',
                'formula': True,
                'table': True,
            })
        
        logger.info(f"🔍 [PROCESS] Processing with {parser} ({parse_method})")
        result = run_async(rag.process_document_complete(**process_kwargs))
        process_duration = time.time() - process_start
        
        # Cleanup
        if temp_file_path and os.path.exists(temp_file_path):
            os.remove(temp_file_path)
        
        total_duration = time.time() - start_time
        logger.info(f"✅ [PROCESS] Completed in {total_duration:.3f}s")
        
        return jsonify({
            "status": "success",
            "result": result,
            "document": {
                "bucket": s3_bucket,
                "key": s3_key,
                "size_mb": round(file_size, 2)
            },
            "parser": {"type": parser, "method": parse_method},
            "timing": {
                "total_duration": round(total_duration, 3),
                "download_duration": round(download_duration, 3),
                "rag_init_duration": round(init_duration, 3),
                "process_duration": round(process_duration, 3)
            }
        })
        
    except Exception as e:
        logger.error(f"❌ [PROCESS] Failed: {str(e)}")
        import traceback
        traceback.print_exc()
        
        if temp_file_path and os.path.exists(temp_file_path):
            try:
                os.remove(temp_file_path)
            except:
                pass
        
        return jsonify({"error": str(e)}), 500

# ============================================================================
# QUERY
# ============================================================================

@app.route('/query', methods=['POST'])
def process_query():
    """Process RAG query"""
    start_time = time.time()
    logger.info("🔍 [QUERY] Query started...")
    
    try:
        data = request.get_json()
        query = data.get('query', '')
        mode = data.get('mode', 'local')
        vlm_enhanced = data.get('vlm_enhanced', False)
        
        if not query:
            return jsonify({"error": "Missing query"}), 400
        
        logger.info(f"❓ [QUERY] '{query[:80]}...'")
        
        # Get RAG instance
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
        logger.info(f"✅ [QUERY] Completed in {total_duration:.3f}s")
        
        return jsonify({
            "query": query,
            "answer": answer,
            "sources": sources,
            "confidence": confidence,
            "mode": mode,
            "vlm_enhanced": vlm_enhanced,
            "status": "completed",
            "timing": {
                "total_duration": round(total_duration, 3),
                "init_duration": round(init_duration, 3),
                "query_duration": round(query_duration, 3)
            }
        })
        
    except Exception as e:
        logger.error(f"❌ [QUERY] Failed: {str(e)}")
        import traceback
        traceback.print_exc()
        
        return jsonify({
            "error": str(e),
            "status": "error"
        }), 500

# ============================================================================
# MULTIMODAL QUERY
# ============================================================================

@app.route('/query_multimodal', methods=['POST'])
def process_multimodal_query():
    """Process multimodal RAG query"""
    start_time = time.time()
    logger.info("🎨 [MULTIMODAL] Starting...")
    
    try:
        data = request.get_json()
        query = data.get('query', '')
        multimodal_content = data.get('multimodal_content', [])
        mode = data.get('mode', 'hybrid')
        
        if not query:
            return jsonify({"error": "Missing query"}), 400
        
        logger.info(f"❓ [MULTIMODAL] Query with {len(multimodal_content)} items")
        
        # Get RAG instance
        init_start = time.time()
        rag = get_rag_instance()
        init_duration = time.time() - init_start
        
        # Process query
        query_start = time.time()
        result = run_async(rag.aquery_with_multimodal(
            query,
            multimodal_content=multimodal_content,
            mode=mode
        ))
        query_duration = time.time() - query_start
        
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
        logger.info(f"✅ [MULTIMODAL] Completed in {total_duration:.3f}s")
        
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
        logger.error(f"❌ [MULTIMODAL] Failed: {str(e)}")
        import traceback
        traceback.print_exc()
        
        return jsonify({
            "error": str(e),
            "status": "error"
        }), 500

# ============================================================================
# EFS ANALYSIS
# ============================================================================

@app.route('/analyze_efs', methods=['GET'])
def analyze_efs():
    """Analyze EFS contents"""
    start_time = time.time()
    logger.info("📊 [EFS_ANALYSIS] Starting...")
    
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
        
        # Walk through EFS
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
                    
                    # Categorize files
                    if file.endswith('.json'):
                        if 'chunk' in file.lower():
                            analysis['chunks'].append(file_info)
                        elif 'embedding' in file.lower():
                            analysis['embeddings'].append(file_info)
                        elif 'metadata' in file.lower() or 'meta' in file.lower():
                            analysis['metadata'].append(file_info)
                        elif 'graph' in file.lower():
                            analysis['graphs'].append(file_info)
                    
                except Exception as e:
                    logger.warning(f"Error processing {file_path}: {e}")
        
        # Sample chunks
        sample_chunks = []
        for chunk_file in analysis['chunks'][:5]:
            try:
                with open(chunk_file['path'], 'r', encoding='utf-8') as f:
                    chunk_data = json.load(f)
                    sample_chunks.append({
                        'file': chunk_file['relative_path'],
                        'content_preview': str(chunk_data)[:200]
                    })
            except Exception as e:
                sample_chunks.append({
                    'file': chunk_file['relative_path'],
                    'error': str(e)
                })
        
        analysis['sample_chunks'] = sample_chunks
        
        total_duration = time.time() - start_time
        logger.info(f"✅ [EFS_ANALYSIS] Completed in {total_duration:.3f}s")
        
        return jsonify({
            'status': 'success',
            'analysis': analysis
        })
        
    except Exception as e:
        logger.error(f"❌ [EFS_ANALYSIS] Failed: {str(e)}")
        return jsonify({'error': str(e)}), 500

@app.route('/get_chunks', methods=['GET'])
def get_chunks():
    """Get full content of all chunks"""
    try:
        rag_output_dir = os.environ.get('RAG_OUTPUT_DIR', '/mnt/efs/rag_output')
        
        chunks_data = {
            'text_chunks': {},
            'entity_chunks': {},
            'relation_chunks': {},
            'vdb_chunks': {},
            'total_chunks': 0
        }
        
        # Read various chunk files
        chunk_files = {
            'text_chunks': f"{rag_output_dir}/kv_store_text_chunks.json",
            'entity_chunks': f"{rag_output_dir}/kv_store_entity_chunks.json",
            'relation_chunks': f"{rag_output_dir}/kv_store_relation_chunks.json",
            'vdb_chunks': f"{rag_output_dir}/vdb_chunks.json"
        }
        
        for key, path in chunk_files.items():
            if os.path.exists(path):
                with open(path, 'r', encoding='utf-8') as f:
                    chunks_data[key] = json.load(f)
                    if key == 'text_chunks':
                        chunks_data['total_chunks'] += len(chunks_data[key])
        
        return jsonify({
            'status': 'success',
            'chunks': chunks_data
        })
        
    except Exception as e:
        logger.error(f"❌ [CHUNKS] Failed: {str(e)}")
        return jsonify({'error': str(e)}), 500

@app.route('/analyze_efs_content', methods=['GET'])
def analyze_efs_content():
    """Download and return content of specific EFS file"""
    try:
        filename = request.args.get('filename')
        if not filename:
            return jsonify({
                'error': 'filename parameter required'
            }), 400
        
        efs_path = os.environ.get('EFS_MOUNT_PATH', '/mnt/efs')
        
        # Search for file
        file_path = None
        for root, dirs, files in os.walk(efs_path):
            if filename in files:
                file_path = os.path.join(root, filename)
                break
        
        if not file_path:
            return jsonify({'error': f'File not found: {filename}'}), 404
        
        # Read file
        file_ext = os.path.splitext(filename)[1].lower()
        
        if file_ext in ['.json', '.txt', '.log', '.md']:
            with open(file_path, 'r', encoding='utf-8') as f:
                content = f.read()
                file_content = {
                    'type': 'text',
                    'content': content,
                    'size': len(content)
                }
        else:
            import base64
            with open(file_path, 'rb') as f:
                binary_content = f.read()
                file_content = {
                    'type': 'binary',
                    'content': base64.b64encode(binary_content).decode('utf-8'),
                    'size': len(binary_content)
                }
        
        return jsonify({
            'status': 'success',
            'filename': filename,
            'path': file_path,
            'content': file_content
        })
        
    except Exception as e:
        logger.error(f"❌ [EFS_CONTENT] Failed: {str(e)}")
        return jsonify({'error': str(e)}), 500

# ============================================================================
# SERVER STARTUP
# ============================================================================

def start_server():
    """Start Flask server"""
    port = int(os.environ.get('PORT', 8000))
    
    logger.info("🚀 [SERVER] Starting RAG-Anything Server...")
    logger.info(f"🔌 [SERVER] Port: {port}")
    logger.info(f"📂 [SERVER] Working Dir: {os.environ.get('OUTPUT_DIR', '/rag-output/')}")
    logger.info(f"🔧 [SERVER] Parser: {os.environ.get('PARSER', 'docling')}")
    
    app.run(
        host='0.0.0.0',
        port=port,
        debug=False,
        threaded=True,
        use_reloader=False
    )

if __name__ == '__main__':
    start_server()