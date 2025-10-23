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
    
    loop = get_event_loop()
    future = asyncio.run_coroutine_threadsafe(coro, loop)
    result = future.result()
    
    logger.info(f"🔄 [ASYNC] Async coroutine completed in {time.time() - start_time:.3f}s")
    return result

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
        parse_method=os.environ.get('PARSE_METHOD', 'ocr'),  # Enable OCR for better text extraction
        enable_image_processing=True,
        enable_table_processing=True,
        enable_equation_processing=True,
        chunk_size=1000,  # Smaller chunks to avoid token limit issues
        chunk_overlap=200,  # Overlap for better context
        max_context_length=4000  # Limit context to avoid token overflow
        # OCR-specific parameters like lang, device, formula, table are passed to process_document_complete()
        # Neo4j-specific optimizations
        # RAG-Anything will use the 1536-dimension embeddings for Neo4j vector indexes
        # This ensures compatibility with Neo4j's vector search capabilities
    )
    
    logger.info(f"⚙️ [CONFIG] RAG configuration loaded in {time.time() - start_time:.3f}s")
    logger.info(f"⚙️ [CONFIG] Working dir: {config.working_dir}")
    logger.info(f"⚙️ [CONFIG] Parser: {config.parser}")
    logger.info(f"⚙️ [CONFIG] Parse method: {config.parse_method}")
    logger.info(f"⚙️ [CONFIG] OCR enabled: {config.parse_method == 'ocr'}")
    logger.info(f"⚙️ [CONFIG] Image processing: {config.enable_image_processing}")
    logger.info(f"⚙️ [CONFIG] Table processing: {config.enable_table_processing}")
    logger.info(f"⚙️ [CONFIG] Equation processing: {config.enable_equation_processing}")
    
    return config

def get_llm_model_func():
    """Create LLM model function with cached config"""
    start_time = time.time()
    logger.info("🤖 [LLM] Creating LLM model function...")
    
    config = get_api_config()
    
    def llm_func(prompt, system_prompt=None, history_messages=[], **kwargs):
        llm_start_time = time.time()
        logger.info(f"🤖 [LLM] Starting LLM completion...")
        logger.info(f"🤖 [LLM] Prompt length: {len(prompt)} characters")
        logger.info(f"🤖 [LLM] System prompt length: {len(system_prompt) if system_prompt else 0} characters")
        logger.info(f"🤖 [LLM] History messages: {len(history_messages)} messages")
        
        # Handle token limits for large prompts
        max_tokens = int(os.environ.get('MAX_TOKENS', '4000'))
        logger.info(f"🤖 [LLM] Max tokens: {max_tokens}")
        
        result = openai_complete_if_cache(
            "gpt-4o-mini",
            prompt,
            system_prompt=system_prompt,
            history_messages=history_messages,
            api_key=config['api_key'],
            base_url=config['base_url'],
            max_tokens=max_tokens,
            **kwargs,
        )
        
        logger.info(f"🤖 [LLM] LLM completion completed in {time.time() - llm_start_time:.3f}s")
        logger.info(f"🤖 [LLM] Response length: {len(result) if result else 0} characters")
        
        return result
    
    logger.info(f"🤖 [LLM] LLM model function created in {time.time() - start_time:.3f}s")
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
    start_time = time.time()
    logger.info("🚀 [RAG_INIT] Getting RAG instance...")
    
    # Thread-safe singleton pattern
    if _rag_instance is None:
        with _rag_lock:
            if _rag_instance is None:
                logger.info("🚀 [RAG_INIT] Creating new RAG-Anything singleton...")
                init_start_time = time.time()
                
                try:
                    logger.info("🚀 [RAG_INIT] Getting configuration...")
                    config = get_rag_config()
                    
                    logger.info("🚀 [RAG_INIT] Getting LLM model function...")
                    llm_func = get_llm_model_func()
                    
                    logger.info("🚀 [RAG_INIT] Getting vision model function...")
                    vision_func = get_vision_model_func(llm_func)
                    
                    logger.info("🚀 [RAG_INIT] Getting embedding function...")
                    embedding_func = get_embedding_func()
                    
                    logger.info("🚀 [RAG_INIT] Initializing RAGAnything...")
                    _rag_instance = RAGAnything(
                        config=config,
                        llm_model_func=llm_func,
                        vision_model_func=vision_func,
                        embedding_func=embedding_func,
                    )
                    
                    logger.info(f"🚀 [RAG_INIT] RAG-Anything singleton initialized successfully in {time.time()-init_start_time:.3f}s")
                    
                except Exception as e:
                    logger.error(f"🚀 [RAG_INIT] Failed to initialize RAG-Anything: {str(e)}")
                    raise
            else:
                logger.info(f"🚀 [RAG_INIT] RAG instance already created by another thread in {time.time() - start_time:.3f}s")
    else:
        logger.info(f"🚀 [RAG_INIT] Using existing RAG instance in {time.time() - start_time:.3f}s")
    
    return _rag_instance

# ============================================================================
# HEALTH CHECK
# ============================================================================

@app.route('/health', methods=['GET'])
def health():
    """Health check endpoint"""
    start_time = time.time()
    logger.info("🏥 [HEALTH] Health check requested...")
    
    try:
        rag_instance = get_rag_instance()
        rag_initialized = rag_instance is not None
        
        response = {
            "status": "healthy",
            "service": "raganything",
            "uptime": time.time() - start_time,
            "rag_initialized": rag_initialized
        }
        
        logger.info(f"🏥 [HEALTH] Health check completed in {time.time() - start_time:.3f}s")
        logger.info(f"🏥 [HEALTH] RAG initialized: {rag_initialized}")
        
        return jsonify(response)
        
    except Exception as e:
        logger.error(f"🏥 [HEALTH] Health check failed: {str(e)}")
        return jsonify({
            "status": "unhealthy",
            "service": "raganything",
            "error": str(e),
            "uptime": time.time() - start_time
        }), 500

# ============================================================================
# DOCUMENT PROCESSING ENDPOINT
# ============================================================================

@app.route('/process', methods=['POST'])
def process_document():
    """Process document from S3 using RAG-Anything"""
    start_time = time.time()
    logger.info("📄 [PROCESS] Document processing started...")
    
    temp_file_path = None
    
    try:
        # Validate request
        data = request.get_json()
        s3_bucket = data.get('bucket')
        s3_key = data.get('key')
        
        if not s3_bucket or not s3_key:
            logger.error("📄 [PROCESS] Missing bucket or key in request")
            return jsonify({"error": "Missing bucket or key"}), 400
        
        logger.info(f"📦 [PROCESS] Processing document: s3://{s3_bucket}/{s3_key}")
        
        # Step 1: Download from S3
        download_start = time.time()
        logger.info("📥 [PROCESS] Starting S3 download...")
        s3_client = boto3.client('s3')
        temp_file_path = f"/tmp/{os.path.basename(s3_key)}"
        s3_client.download_file(s3_bucket, s3_key, temp_file_path)
        download_duration = time.time() - download_start
        
        file_size = os.path.getsize(temp_file_path) / (1024 * 1024)  # MB
        logger.info(f"📥 [PROCESS] Downloaded {file_size:.2f}MB in {download_duration:.3f}s")
        
        # Step 2: Get RAG instance (lazy init on first call)
        init_start = time.time()
        logger.info("🚀 [PROCESS] Getting RAG instance...")
        rag = get_rag_instance()
        init_duration = time.time() - init_start
        logger.info(f"🚀 [PROCESS] RAG instance ready in {init_duration:.3f}s")
        
        # Step 3: Process document
        process_start = time.time()
        parser = os.environ.get('PARSER', 'docling')
        parse_method = os.environ.get('PARSE_METHOD', 'auto')
        
        logger.info(f"🔧 [PROCESS] Using parser: {parser}, method: {parse_method}")
        
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
        
        logger.info(f"🔍 [PROCESS] Processing with {parser} parser ({parse_method} mode)")
        result = run_async(rag.process_document_complete(**process_kwargs))
        process_duration = time.time() - process_start
        
        logger.info(f"💾 [PROCESS] Document processed in {process_duration:.3f}s")
        
        # Step 4: Cleanup
        if temp_file_path and os.path.exists(temp_file_path):
            os.remove(temp_file_path)
            logger.info(f"🧹 [PROCESS] Temp file cleaned up")
        
        total_duration = time.time() - start_time
        logger.info(f"✅ [PROCESS] Document processing completed successfully in {total_duration:.3f}s")
        
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
        logger.error(f"❌ [PROCESS] Document processing failed after {total_duration:.3f}s: {str(e)}")
        
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
    logger.info("🔍 [QUERY] RAG query started...")
    
    try:
        # Validate request
        data = request.get_json()
        query = data.get('query', '')
        mode = data.get('mode', 'local')  # Use local mode to avoid VLM issues
        vlm_enhanced = False  # Disable VLM processing to avoid async errors
        
        if not query:
            logger.error("🔍 [QUERY] Missing query in request")
            return jsonify({"error": "Missing query"}), 400
        
        logger.info(f"❓ [QUERY] Processing query: '{query[:80]}{'...' if len(query) > 80 else ''}'")
        logger.info(f"⚙️ [QUERY] Mode: {mode}, VLM: {vlm_enhanced if vlm_enhanced is not None else 'auto'}")
        
        # Get RAG instance (reuses existing singleton)
        init_start = time.time()
        logger.info("🚀 [QUERY] Getting RAG instance...")
        rag = get_rag_instance()
        init_duration = time.time() - init_start
        logger.info(f"🚀 [QUERY] RAG instance ready in {init_duration:.3f}s")
        
        # Process query
        query_start = time.time()
        logger.info("🔍 [QUERY] Starting query processing...")
        query_kwargs = {'mode': mode}
        if vlm_enhanced is not None:
            query_kwargs['vlm_enhanced'] = vlm_enhanced
        
        result = run_async(rag.aquery(query, **query_kwargs))
        query_duration = time.time() - query_start
        
        logger.info(f"📊 [QUERY] Query processed in {query_duration:.3f}s")
        
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
        logger.info(f"✅ [QUERY] Query completed successfully in {total_duration:.3f}s")
        
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
        logger.error(f"❌ [QUERY] Query processing failed after {total_duration:.3f}s: {str(e)}")
        
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
    start_time = time.time()
    logger.info("📊 [EFS_ANALYSIS] EFS analysis started...")
    
    try:
        efs_path = os.environ.get('EFS_MOUNT_PATH', '/mnt/efs')
        rag_output_dir = os.environ.get('RAG_OUTPUT_DIR', '/mnt/efs/rag_output')
        
        logger.info(f"📊 [EFS_ANALYSIS] Analyzing EFS path: {efs_path}")
        logger.info(f"📊 [EFS_ANALYSIS] RAG output dir: {rag_output_dir}")
        
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
            logger.error(f"📊 [EFS_ANALYSIS] EFS path {efs_path} not found")
            return jsonify({
                'error': f'EFS path {efs_path} not found',
                'analysis': analysis
            }), 404
        
        logger.info("📊 [EFS_ANALYSIS] Walking through EFS directory...")
        walk_start = time.time()
        
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
                    logger.warning(f"📊 [EFS_ANALYSIS] Error processing file {file_path}: {str(e)}")
                    analysis['files'].append({
                        'path': file_path,
                        'name': file,
                        'error': str(e)
                    })
        
        walk_duration = time.time() - walk_start
        logger.info(f"📊 [EFS_ANALYSIS] Directory walk completed in {walk_duration:.3f}s")
        logger.info(f"📊 [EFS_ANALYSIS] Found {analysis['total_files']} files, {len(analysis['chunks'])} chunks, {len(analysis['embeddings'])} embeddings")
        
        # Try to read some sample chunk files to show content
        logger.info("📊 [EFS_ANALYSIS] Reading sample chunk files...")
        sample_chunks = []
        for chunk_file in analysis['chunks'][:5]:  # First 5 chunk files
            try:
                with open(chunk_file['path'], 'r', encoding='utf-8') as f:
                    chunk_data = json.load(f)
                    
                    # For text chunks, show full content, for others show preview
                    if 'text_chunks' in chunk_file['name']:
                        sample_chunks.append({
                            'file': chunk_file['relative_path'],
                            'full_content': chunk_data,
                            'content_type': 'text_chunks'
                        })
                    else:
                        sample_chunks.append({
                            'file': chunk_file['relative_path'],
                            'content_preview': str(chunk_data)[:200] + '...' if len(str(chunk_data)) > 200 else str(chunk_data),
                            'content_type': 'other'
                        })
            except Exception as e:
                logger.warning(f"📊 [EFS_ANALYSIS] Error reading chunk file {chunk_file['path']}: {str(e)}")
                sample_chunks.append({
                    'file': chunk_file['relative_path'],
                    'error': str(e)
                })
        
        analysis['sample_chunks'] = sample_chunks
        
        # Try to read some sample metadata files
        logger.info("📊 [EFS_ANALYSIS] Reading sample metadata files...")
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
                logger.warning(f"📊 [EFS_ANALYSIS] Error reading metadata file {meta_file['path']}: {str(e)}")
                sample_metadata.append({
                    'file': meta_file['relative_path'],
                    'error': str(e)
                })
        
        analysis['sample_metadata'] = sample_metadata
        
        total_duration = time.time() - start_time
        logger.info(f"✅ [EFS_ANALYSIS] EFS analysis completed successfully in {total_duration:.3f}s")
        
        return jsonify({
            'status': 'success',
            'analysis': analysis
        })
        
    except Exception as e:
        total_duration = time.time() - start_time
        logger.error(f"❌ [EFS_ANALYSIS] EFS analysis failed after {total_duration:.3f}s: {str(e)}")
        
        return jsonify({
            'error': str(e),
            'status': 'error'
        }), 500

@app.route('/get_chunks', methods=['GET'])
def get_chunks():
    """Get full content of all chunks"""
    start_time = time.time()
    logger.info("📄 [CHUNKS] Getting full chunk content...")
    
    try:
        efs_path = os.environ.get('EFS_MOUNT_PATH', '/mnt/efs')
        rag_output_dir = os.environ.get('RAG_OUTPUT_DIR', '/mnt/efs/rag_output')
        
        chunks_data = {
            'text_chunks': {},
            'entity_chunks': {},
            'relation_chunks': {},
            'vdb_chunks': {},
            'total_chunks': 0
        }
        
        # Read text chunks
        text_chunks_path = f"{rag_output_dir}/kv_store_text_chunks.json"
        if os.path.exists(text_chunks_path):
            logger.info("📄 [CHUNKS] Reading text chunks...")
            with open(text_chunks_path, 'r', encoding='utf-8') as f:
                chunks_data['text_chunks'] = json.load(f)
                chunks_data['total_chunks'] += len(chunks_data['text_chunks'])
        
        # Read entity chunks
        entity_chunks_path = f"{rag_output_dir}/kv_store_entity_chunks.json"
        if os.path.exists(entity_chunks_path):
            logger.info("📄 [CHUNKS] Reading entity chunks...")
            with open(entity_chunks_path, 'r', encoding='utf-8') as f:
                chunks_data['entity_chunks'] = json.load(f)
        
        # Read relation chunks
        relation_chunks_path = f"{rag_output_dir}/kv_store_relation_chunks.json"
        if os.path.exists(relation_chunks_path):
            logger.info("📄 [CHUNKS] Reading relation chunks...")
            with open(relation_chunks_path, 'r', encoding='utf-8') as f:
                chunks_data['relation_chunks'] = json.load(f)
        
        # Read VDB chunks (vector database)
        vdb_chunks_path = f"{rag_output_dir}/vdb_chunks.json"
        if os.path.exists(vdb_chunks_path):
            logger.info("📄 [CHUNKS] Reading VDB chunks...")
            with open(vdb_chunks_path, 'r', encoding='utf-8') as f:
                chunks_data['vdb_chunks'] = json.load(f)
        
        total_duration = time.time() - start_time
        logger.info(f"✅ [CHUNKS] Retrieved {chunks_data['total_chunks']} chunks in {total_duration:.3f}s")
        
        return jsonify({
            'status': 'success',
            'chunks': chunks_data,
            'timing': {
                'total_duration': round(total_duration, 3)
            }
        })
        
    except Exception as e:
        total_duration = time.time() - start_time
        logger.error(f"❌ [CHUNKS] Failed to get chunks after {total_duration:.3f}s: {str(e)}")
        
        return jsonify({
            'error': str(e),
            'status': 'error'
        }), 500

# ============================================================================
# EFS CONTENT ANALYSIS ENDPOINT
# ============================================================================

@app.route('/analyze_efs_content', methods=['GET'])
def analyze_efs_content():
    """Download and return the content of a specific EFS file"""
    start_time = time.time()
    logger.info("📊 [EFS_CONTENT] EFS single file download started...")
    
    try:
        # Get filename from query parameters
        filename = request.args.get('filename')
        if not filename:
            return jsonify({
                'error': 'filename parameter is required',
                'usage': 'GET /analyze_efs_content?filename=your-file-name.json'
            }), 400
        
        efs_path = os.environ.get('EFS_MOUNT_PATH', '/mnt/efs')
        rag_output_dir = os.environ.get('RAG_OUTPUT_DIR', '/mnt/efs/rag_output')
        
        logger.info(f"📊 [EFS_CONTENT] Downloading file: {filename}")
        logger.info(f"📊 [EFS_CONTENT] EFS path: {efs_path}")
        logger.info(f"📊 [EFS_CONTENT] RAG output dir: {rag_output_dir}")
        
        analysis = {
            'efs_path': efs_path,
            'rag_output_dir': rag_output_dir,
            'efs_exists': os.path.exists(efs_path),
            'rag_output_exists': os.path.exists(rag_output_dir),
            'requested_filename': filename,
            'file_info': {},
            'file_content': {},
            'download_status': 'pending'
        }
        
        if not os.path.exists(efs_path):
            logger.error(f"📊 [EFS_CONTENT] EFS path {efs_path} not found")
            return jsonify({
                'error': f'EFS path {efs_path} not found',
                'analysis': analysis
            }), 404
        
        # Search for the file in EFS
        logger.info(f"🔍 [EFS_CONTENT] Searching for file: {filename}")
        file_found = False
        file_path = None
        
        # First try exact match in rag_output_dir
        potential_paths = [
            os.path.join(rag_output_dir, filename),
            os.path.join(efs_path, filename),
            os.path.join(efs_path, 'rag_output', filename)
        ]
        
        # Also search recursively for the filename
        for root, dirs, files in os.walk(efs_path):
            if filename in files:
                file_path = os.path.join(root, filename)
                file_found = True
                break
        
        # If not found recursively, try the potential paths
        if not file_found:
            for path in potential_paths:
                if os.path.exists(path):
                    file_path = path
                    file_found = True
                    break
        
        if not file_found:
            logger.error(f"📊 [EFS_CONTENT] File not found: {filename}")
            return jsonify({
                'error': f'File not found: {filename}',
                'searched_paths': potential_paths,
                'analysis': analysis
            }), 404
        
        logger.info(f"✅ [EFS_CONTENT] File found at: {file_path}")
        
        # Get file information
        try:
            file_size = os.path.getsize(file_path)
            file_stat = os.stat(file_path)
            file_ext = os.path.splitext(filename)[1].lower()
            relative_path = os.path.relpath(file_path, efs_path)
            
            file_info = {
                'name': filename,
                'path': file_path,
                'relative_path': relative_path,
                'directory': os.path.dirname(file_path),
                'size_bytes': file_size,
                'size_mb': round(file_size / (1024 * 1024), 3),
                'extension': file_ext,
                'created_date': time.strftime('%Y-%m-%d %H:%M:%S', time.localtime(file_stat.st_ctime)),
                'modified_date': time.strftime('%Y-%m-%d %H:%M:%S', time.localtime(file_stat.st_mtime)),
                'accessed_date': time.strftime('%Y-%m-%d %H:%M:%S', time.localtime(file_stat.st_atime))
            }
            
            analysis['file_info'] = file_info
            
        except Exception as e:
            logger.error(f"❌ [EFS_CONTENT] Error getting file info for {file_path}: {str(e)}")
            return jsonify({
                'error': f'Error getting file info: {str(e)}',
                'analysis': analysis
            }), 500
        
        # Download file content
        logger.info(f"📥 [EFS_CONTENT] Downloading file content: {filename}")
        download_start = time.time()
        
        try:
            if file_ext in ['.json', '.md', '.txt', '.log', '.csv', '.xml', '.yaml', '.yml', '.py', '.js', '.html', '.css']:
                # Text files - read as text
                with open(file_path, 'r', encoding='utf-8') as f:
                    content = f.read()
                    analysis['file_content'] = {
                        'type': 'text',
                        'content': content,
                        'encoding': 'utf-8',
                        'size': len(content),
                        'lines': len(content.splitlines()) if content else 0
                    }
                    
            elif file_ext in ['.pdf', '.docx', '.doc', '.xlsx', '.pptx', '.zip', '.tar', '.gz', '.png', '.jpg', '.jpeg', '.gif']:
                # Binary files - read as base64
                with open(file_path, 'rb') as f:
                    binary_content = f.read()
                    import base64
                    base64_content = base64.b64encode(binary_content).decode('utf-8')
                    analysis['file_content'] = {
                        'type': 'binary',
                        'content': base64_content,
                        'encoding': 'base64',
                        'size': len(binary_content),
                        'original_size': file_size,
                        'note': 'Use base64 decode to get original binary content'
                    }
                    
            else:
                # Unknown files - try as text first, then binary
                try:
                    with open(file_path, 'r', encoding='utf-8') as f:
                        content = f.read()
                        analysis['file_content'] = {
                            'type': 'text',
                            'content': content,
                            'encoding': 'utf-8',
                            'size': len(content),
                            'lines': len(content.splitlines()) if content else 0,
                            'note': 'Read as text (unknown extension)'
                        }
                except:
                    # Fallback to binary
                    with open(file_path, 'rb') as f:
                        binary_content = f.read()
                        import base64
                        base64_content = base64.b64encode(binary_content).decode('utf-8')
                        analysis['file_content'] = {
                            'type': 'binary',
                            'content': base64_content,
                            'encoding': 'base64',
                            'size': len(binary_content),
                            'original_size': file_size,
                            'note': 'Read as binary (unknown extension)'
                        }
            
            download_duration = time.time() - download_start
            analysis['download_status'] = 'success'
            
            logger.info(f"✅ [EFS_CONTENT] Successfully downloaded: {filename} ({file_size} bytes) in {download_duration:.3f}s")
            
        except Exception as e:
            download_duration = time.time() - download_start
            logger.error(f"❌ [EFS_CONTENT] Error downloading file {file_path}: {str(e)}")
            analysis['download_status'] = 'error'
            analysis['file_content'] = {
                'type': 'error',
                'error': str(e),
                'size': 0
            }
            
            return jsonify({
                'error': f'Error downloading file: {str(e)}',
                'analysis': analysis,
                'timing': {'download_duration': round(download_duration, 3)}
            }), 500
        
        total_duration = time.time() - start_time
        logger.info(f"✅ [EFS_CONTENT] File download completed successfully in {total_duration:.3f}s")
        
        return jsonify({
            'status': 'success',
            'analysis': analysis,
            'timing': {
                'total_duration': round(total_duration, 3),
                'download_duration': round(download_duration, 3)
            }
        })
        
    except Exception as e:
        total_duration = time.time() - start_time
        logger.error(f"❌ [EFS_CONTENT] EFS content analysis failed after {total_duration:.3f}s: {str(e)}")
        
        import traceback
        traceback.print_exc()
        
        return jsonify({
            'error': str(e),
            'status': 'error',
            'timing': {'total_duration': round(total_duration, 3)}
        }), 500

# ============================================================================
# SERVER STARTUP
# ============================================================================

def start_server():
    """Start the Flask server"""
    port = int(os.environ.get('PORT', 8000))
    
    logger.info("🚀 [SERVER] Starting RAG-Anything Server...")
    logger.info(f"📍 [SERVER] Port: {port}")
    logger.info(f"📂 [SERVER] Working Dir: {os.environ.get('OUTPUT_DIR', '/rag-output/')}")
    logger.info(f"🔧 [SERVER] Parser: {os.environ.get('PARSER', 'docling')}")
    logger.info(f"📝 [SERVER] Parse Method: {os.environ.get('PARSE_METHOD', 'auto')}")
    logger.info(f"🔄 [SERVER] Lazy Init: RAG instance created on first request")
    logger.info("🚀 [SERVER] Server starting...")
    
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