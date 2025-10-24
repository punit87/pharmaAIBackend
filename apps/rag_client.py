#!/usr/bin/env python3
"""
RAG-Anything Server - Optimized for ECS Tasks
- Persistent event loop for efficient async operations
- Lazy initialization to reduce cold start time
- Proper resource cleanup
- Memory-efficient caching
- Fixed async handling matching RAG-Anything reference implementation
- Using standard RAG-Anything chunking approach (no custom LLM chunking)
"""
import os
import time
import json
import boto3
import asyncio
import threading
import atexit
import logging
import pandas as pd
import io
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
        # Make timeout configurable
        timeout = int(os.environ.get('ASYNC_TIMEOUT', '300'))
        result = future.result(timeout=timeout)
        
        exec_time = time.time() - start_time
        logger.info(f"🔄 [ASYNC] Async coroutine completed in {exec_time:.3f}s")
        return result
    except Exception as e:
        exec_time = time.time() - start_time
        logger.error(f"❌ [ASYNC] Async coroutine failed after {exec_time:.3f}s: {str(e)}")
        raise e

def cleanup_event_loop():
    """Cleanup event loop on shutdown"""
    global _event_loop
    try:
        if _event_loop and not _event_loop.is_closed():
            _event_loop.call_soon_threadsafe(_event_loop.stop)
            _event_loop.close()
            logger.info("✅ [EVENT_LOOP] Event loop cleaned up successfully")
    except Exception as e:
        logger.error(f"❌ [EVENT_LOOP] Error cleaning up event loop: {e}")

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
    start_time = time.time()
    api_key = os.environ.get('OPENAI_API_KEY')
    base_url = os.environ.get('OPENAI_BASE_URL')
    
    if not api_key:
        raise ValueError("OPENAI_API_KEY environment variable is required")
    if not base_url:
        raise ValueError("OPENAI_BASE_URL environment variable is required")
    
    exec_time = time.time() - start_time
    logger.info(f"⚙️ [CONFIG] API config loaded in {exec_time:.3f}s")
    return {
        'api_key': api_key,
        'base_url': base_url,
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
        enable_table_processing=False,
        enable_equation_processing=True
    )
    
    exec_time = time.time() - start_time
    logger.info(f"⚙️ [CONFIG] RAG configuration loaded in {exec_time:.3f}s")
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
    
    exec_time = time.time() - start_time
    logger.info(f"🤖 [LLM] LLM model function created in {exec_time:.3f}s")
    return llm_func

def get_vision_model_func(llm_func):
    """
    Create vision model function - SYNCHRONOUS wrapper that returns coroutine
    This matches the RAG-Anything reference implementation
    """
    start_time = time.time()
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
            # Build messages list without None values
            vision_messages = []
            if system_prompt:
                vision_messages.append({"role": "system", "content": system_prompt})
            
            vision_messages.append({
                "role": "user",
                "content": [
                    {"type": "text", "text": prompt},
                    {
                        "type": "image_url",
                        "image_url": {"url": f"data:image/jpeg;base64,{image_data}"}
                    }
                ]
            })
            
            return openai_complete_if_cache(
                "gpt-4o", "", system_prompt=None, history_messages=[],
                messages=vision_messages,
                api_key=config['api_key'], base_url=config['base_url'], **kwargs
            )
        # Pure text fallback
        else:
            return llm_func(prompt, system_prompt, history_messages, **kwargs)
    
    exec_time = time.time() - start_time
    logger.info(f"🤖 [VISION] Vision model function created in {exec_time:.3f}s")
    return vision_func

def get_embedding_func():
    """
    Create embedding function - handles both sync and async contexts
    
    Using text-embedding-ada-002 for Neo4j compatibility:
    - Dimensions: 1536 (Neo4j standard)
    - Cost: $0.0001 per 1K tokens (most cost-effective)
    - Neo4j Support: Full compatibility with vector indexes
    
    FIXED: Properly handles input validation and returns coroutine
    """
    start_time = time.time()
    config = get_api_config()
    
    async def safe_embed_async(texts):
        """
        Async embedding function that properly formats input for OpenAI API
        """
        embed_start = time.time()
        try:
            # Ensure texts is in the correct format
            if isinstance(texts, str):
                # Single text - convert to list
                input_texts = [texts.strip()]
            elif isinstance(texts, list):
                # Multiple texts - ensure all are strings and not empty
                input_texts = []
                for t in texts:
                    if t is not None:
                        text_str = str(t).strip()
                        if text_str:
                            input_texts.append(text_str)
                
                # Fail fast if no valid texts
                if not input_texts:
                    raise ValueError("No valid text inputs provided for embedding")
            else:
                logger.warning(f"⚠️ [EMBEDDING] Unexpected input type: {type(texts)}, converting to string")
                input_texts = [str(texts).strip()]
            
            # Validate we have content
            if not input_texts or not any(input_texts):
                raise ValueError(f"Empty or invalid text input for embedding: {texts}")
            
            # Log for debugging
            logger.info(f"📊 [EMBEDDING] Processing {len(input_texts)} text(s)")
            logger.debug(f"📊 [EMBEDDING] First text preview: {input_texts[0][:100]}...")
            
            # Call the OpenAI embedding API
            result = await openai_embed(
                texts=input_texts,
                model="text-embedding-ada-002",
                api_key=config['api_key'],
                base_url=config['base_url'],
            )
            
            embed_time = time.time() - embed_start
            logger.info(f"✅ [EMBEDDING] Successfully generated {len(result)} embedding(s) in {embed_time:.3f}s")
            
            # Validate output
            if not result or not isinstance(result, list):
                raise ValueError(f"Invalid embedding result: {type(result)}")
            
            return result
            
        except Exception as e:
            embed_time = time.time() - embed_start
            logger.error(f"❌ [EMBEDDING] Error during embedding after {embed_time:.3f}s: {e}")
            logger.error(f"❌ [EMBEDDING] Input type: {type(texts)}")
            if isinstance(texts, (list, str)):
                logger.error(f"❌ [EMBEDDING] Input preview: {str(texts)[:300]}")
            raise e
    
    def safe_embed_sync(texts):
        """
        Synchronous wrapper that returns the coroutine
        RAG-Anything will await it in its own async context
        """
        return safe_embed_async(texts)
    
    exec_time = time.time() - start_time
    logger.info(f"📊 [EMBEDDING] Embedding function created in {exec_time:.3f}s")
    return EmbeddingFunc(
        embedding_dim=1536,
        max_token_size=8191,
        func=safe_embed_sync,
    )

# ============================================================================
# LAZY RAG INITIALIZATION
# ============================================================================

def get_rag_instance():
    """Get or create singleton RAG instance with proper thread safety"""
    global _rag_instance
    start_time = time.time()
    logger.info("🚀 [RAG_INIT] Getting RAG instance...")
    
    # Quick check without lock (optimization)
    if _rag_instance is not None:
        logger.info(f"🚀 [RAG_INIT] Using cached RAG instance in {time.time() - start_time:.3f}s")
        return _rag_instance
    
    # Double-check with lock
    with _rag_lock:
        if _rag_instance is None:
            logger.info("🚀 [RAG_INIT] Creating new RAG-Anything singleton...")
            
            init_start = time.time()
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
                
                init_time = time.time() - init_start
                logger.info(f"🚀 [RAG_INIT] Initialized in {init_time:.3f}s")
                
            except Exception as e:
                init_time = time.time() - init_start
                logger.error(f"🚀 [RAG_INIT] Failed after {init_time:.3f}s: {str(e)}")
                raise
    
    exec_time = time.time() - start_time
    logger.info(f"🚀 [RAG_INIT] RAG instance ready in {exec_time:.3f}s")
    return _rag_instance

# ============================================================================
# HEALTH CHECK
# ============================================================================

@app.route('/health', methods=['GET'])
def health():
    """Health check endpoint"""
    start_time = time.time()
    logger.info("🩺 [HEALTH] Health check started...")
    try:
        rag_instance = get_rag_instance()
        total_time = time.time() - start_time
        logger.info(f"✅ [HEALTH] Health check completed in {total_time:.3f}s")
        return jsonify({
            "status": "healthy",
            "service": "raganything",
            "rag_initialized": rag_instance is not None,
            "timing": {
                "total_duration": round(total_time, 3)
            }
        })
    except Exception as e:
        total_time = time.time() - start_time
        logger.error(f"❌ [HEALTH] Health check failed after {total_time:.3f}s: {str(e)}")
        return jsonify({
            "status": "unhealthy",
            "error": str(e),
            "timing": {
                "total_duration": round(total_time, 3)
            }
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
    timing = {}
    
    try:
        # Validate API configuration first
        config_start = time.time()
        try:
            get_api_config()
        except ValueError as e:
            config_time = time.time() - config_start
            logger.error(f"❌ [PROCESS] Configuration error after {config_time:.3f}s: {str(e)}")
            timing["config_validation"] = round(config_time, 3)
            return jsonify({"error": f"Configuration error: {str(e)}", "timing": timing}), 500
        
        config_time = time.time() - config_start
        timing["config_validation"] = round(config_time, 3)
        logger.info(f"⚙️ [PROCESS] Config validated in {config_time:.3f}s")
        
        data = request.get_json()
        s3_bucket = data.get('bucket')
        s3_key = data.get('key')
        
        if not s3_bucket or not s3_key:
            total_time = time.time() - start_time
            timing["total_duration"] = round(total_time, 3)
            return jsonify({"error": "Missing bucket or key", "timing": timing}), 400
        
        logger.info(f"📦 [PROCESS] s3://{s3_bucket}/{s3_key}")
        
        # Download from S3
        download_start = time.time()
        s3_client = boto3.client('s3')
        temp_file_path = f"/tmp/{os.path.basename(s3_key)}"
        s3_client.download_file(s3_bucket, s3_key, temp_file_path)
        download_duration = time.time() - download_start
        timing["download_duration"] = round(download_duration, 3)
        file_size = os.path.getsize(temp_file_path) / (1024 * 1024)
        logger.info(f"📥 [PROCESS] Downloaded {file_size:.2f}MB in {download_duration:.3f}s")
        
        # Get RAG instance
        rag_init_start = time.time()
        rag = get_rag_instance()
        rag_init_duration = time.time() - rag_init_start
        timing["rag_init_duration"] = round(rag_init_duration, 3)
        logger.info(f"🚀 [PROCESS] RAG initialized in {rag_init_duration:.3f}s")
        
        # Process document with custom table chunking
        process_start = time.time()
        parser = os.environ.get('PARSER', 'docling')
        parse_method = os.environ.get('PARSE_METHOD', 'ocr')
        
        logger.info(f"🔍 [PROCESS] Processing with {parser} ({parse_method})")
        logger.info(f"🔍 [PROCESS] Using custom table chunking approach")
        
        try:
            # Step 1: Parse document to get content_list
            logger.info("📋 [PROCESS] Parsing document to get content list...")
            content_list = run_async(rag.parse_document(temp_file_path, parse_method=parse_method))
            logger.info(f"📋 [PROCESS] Parsed {len(content_list)} content items")
            
            # Step 2: Convert table items to text items
            modified_content_list = []
            table_count = 0
            
            for item in content_list:
                # Check if item is a dictionary and has the expected structure
                if not isinstance(item, dict):
                    logger.warning(f"⚠️ [PROCESS] Skipping non-dict item: {type(item)}")
                    modified_content_list.append(item)
                    continue
                    
                if item.get('type') == 'table':
                    table_count += 1
                    logger.info(f"📊 [PROCESS] Processing table {table_count}: {item.get('title', 'Untitled')}")
                    
                    # Extract table body (markdown format)
                    table_body = item.get('body', '')
                    if not table_body:
                        logger.warning(f"⚠️ [PROCESS] Table {table_count} has no body content")
                        continue
                    
                    try:
                        # Parse markdown table with pandas
                        df = pd.read_csv(io.StringIO(table_body), sep='|', skipinitialspace=True)
                        
                        # Clean up the dataframe (remove empty columns and rows)
                        df = df.dropna(how='all').dropna(axis=1, how='all')
                        
                        # Remove extra whitespace from column names
                        df.columns = df.columns.str.strip()
                        
                        logger.info(f"📊 [PROCESS] Table {table_count}: {len(df)} rows, {len(df.columns)} columns")
                        
                        # Convert each row to a text chunk
                        for idx, row in df.iterrows():
                            # Create a readable Q&A format
                            if len(df.columns) >= 2:
                                # Assume first column is question, second is answer
                                question = str(row.iloc[0]).strip()
                                answer = str(row.iloc[1]).strip()
                                
                                if question and answer and question != 'nan' and answer != 'nan':
                                    # Create text chunk in Q&A format
                                    qa_text = f"Question: {question}\nAnswer: {answer}"
                                    
                                    text_item = {
                                        'type': 'text',
                                        'title': f"Q&A Row {idx + 1}",
                                        'body': qa_text,
                                        'source': item.get('source', ''),
                                        'page': item.get('page', 1)
                                    }
                                    modified_content_list.append(text_item)
                                    
                                    logger.info(f"📝 [PROCESS] Created Q&A chunk: {question[:50]}...")
                        
                        logger.info(f"✅ [PROCESS] Converted table {table_count} to {len(df)} Q&A chunks")
                        
                    except Exception as table_error:
                        logger.error(f"❌ [PROCESS] Failed to process table {table_count}: {str(table_error)}")
                        # Fallback: add original table as text
                        text_item = {
                            'type': 'text',
                            'title': item.get('title', 'Table'),
                            'body': table_body,
                            'source': item.get('source', ''),
                            'page': item.get('page', 1)
                        }
                        modified_content_list.append(text_item)
                else:
                    # Keep non-table items as-is
                    modified_content_list.append(item)
            
            logger.info(f"📊 [PROCESS] Processed {table_count} tables, created {len(modified_content_list)} total chunks")
            
            # Step 3: Insert modified content list
            logger.info("💾 [PROCESS] Inserting modified content list...")
            result = run_async(rag.insert_content_list(modified_content_list, doc_id=s3_key))
            
            logger.info("✅ [PROCESS] Document processing completed successfully")
            
        except Exception as proc_error:
            process_duration = time.time() - process_start
            timing["process_duration"] = round(process_duration, 3)
            logger.error(f"❌ [PROCESS] Processing error after {process_duration:.3f}s: {str(proc_error)}")
            
            # Check if it's an embedding error
            if "400" in str(proc_error) and "input" in str(proc_error).lower():
                logger.error("❌ [PROCESS] OpenAI embedding API error - likely malformed input")
                logger.error("❌ [PROCESS] This suggests the embedding function received invalid data")
                raise Exception(f"Embedding API error: {str(proc_error)}. Check that text chunks are properly formatted.")
            else:
                raise proc_error
        
        process_duration = time.time() - process_start
        timing["process_duration"] = round(process_duration, 3)
        logger.info(f"🔍 [PROCESS] Document processed in {process_duration:.3f}s")
        
        # Cleanup
        cleanup_start = time.time()
        if temp_file_path and os.path.exists(temp_file_path):
            os.remove(temp_file_path)
        cleanup_time = time.time() - cleanup_start
        timing["cleanup_duration"] = round(cleanup_time, 3)
        logger.info(f"🧹 [PROCESS] Cleanup completed in {cleanup_time:.3f}s")
        
        total_duration = time.time() - start_time
        timing["total_duration"] = round(total_duration, 3)
        logger.info(f"✅ [PROCESS] Completed in {total_duration:.3f}s")
        
        response = {
            "status": "success",
            "result": result,
            "document": {
                "bucket": s3_bucket,
                "key": s3_key,
                "size_mb": round(file_size, 2)
            },
            "parser": {"type": parser, "method": parse_method},
            "chunking": "custom_table_chunking",
            "timing": timing
        }
        
        return jsonify(response)
        
    except Exception as e:
        total_duration = time.time() - start_time
        timing["total_duration"] = round(total_duration, 3)
        logger.error(f"❌ [PROCESS] Failed after {total_duration:.3f}s: {str(e)}")
        import traceback
        traceback.print_exc()
        
        if temp_file_path and os.path.exists(temp_file_path):
            try:
                os.remove(temp_file_path)
            except:
                pass
        
        return jsonify({"error": str(e), "timing": timing}), 500

# ============================================================================
# QUERY
# ============================================================================

@app.route('/query', methods=['POST'])
def process_query():
    """Process RAG query"""
    start_time = time.time()
    logger.info("🔍 [QUERY] Query started...")
    timing = {}
    
    try:
        data = request.get_json()
        query = data.get('query', '')
        mode = data.get('mode', 'local')
        vlm_enhanced = data.get('vlm_enhanced', False)
        
        if not query:
            total_time = time.time() - start_time
            timing["total_duration"] = round(total_time, 3)
            return jsonify({"error": "Missing query", "timing": timing}), 400
        
        logger.info(f"❓ [QUERY] '{query[:80]}...'")
        
        # Get RAG instance
        rag_init_start = time.time()
        rag = get_rag_instance()
        rag_init_duration = time.time() - rag_init_start
        timing["init_duration"] = round(rag_init_duration, 3)
        logger.info(f"🚀 [QUERY] RAG initialized in {rag_init_duration:.3f}s")
        
        # Process query
        query_proc_start = time.time()
        query_kwargs = {'mode': mode}
        if vlm_enhanced is not None:
            query_kwargs['vlm_enhanced'] = vlm_enhanced
        
        result = run_async(rag.aquery(query, **query_kwargs))
        query_duration = time.time() - query_proc_start
        timing["query_duration"] = round(query_duration, 3)
        logger.info(f"🔍 [QUERY] Query processed in {query_duration:.3f}s")
        
        # Parse result
        parse_start = time.time()
        if isinstance(result, dict):
            answer = result.get('answer', str(result))
            sources = result.get('sources', [])
            confidence = result.get('confidence', 0.0)
        else:
            answer = str(result)
            sources = []
            confidence = 0.0
        parse_time = time.time() - parse_start
        timing["parse_duration"] = round(parse_time, 3)
        logger.info(f"📝 [QUERY] Result parsed in {parse_time:.3f}s")
        
        total_duration = time.time() - start_time
        timing["total_duration"] = round(total_duration, 3)
        logger.info(f"✅ [QUERY] Completed in {total_duration:.3f}s")
        
        return jsonify({
            "query": query,
            "answer": answer,
            "sources": sources,
            "confidence": confidence,
            "mode": mode,
            "vlm_enhanced": vlm_enhanced,
            "status": "completed",
            "timing": timing
        })
        
    except Exception as e:
        total_duration = time.time() - start_time
        timing["total_duration"] = round(total_duration, 3)
        logger.error(f"❌ [QUERY] Failed after {total_duration:.3f}s: {str(e)}")
        import traceback
        traceback.print_exc()
        
        return jsonify({
            "error": str(e),
            "status": "error",
            "timing": timing
        }), 500

# ============================================================================
# MULTIMODAL QUERY
# ============================================================================

@app.route('/query_multimodal', methods=['POST'])
def process_multimodal_query():
    """Process multimodal RAG query"""
    start_time = time.time()
    logger.info("🎨 [MULTIMODAL] Starting...")
    timing = {}
    
    try:
        data = request.get_json()
        query = data.get('query', '')
        multimodal_content = data.get('multimodal_content', [])
        mode = data.get('mode', 'hybrid')
        
        if not query:
            total_time = time.time() - start_time
            timing["total_duration"] = round(total_time, 3)
            return jsonify({"error": "Missing query", "timing": timing}), 400
        
        logger.info(f"❓ [MULTIMODAL] Query with {len(multimodal_content)} items")
        
        # Get RAG instance
        rag_init_start = time.time()
        rag = get_rag_instance()
        rag_init_duration = time.time() - rag_init_start
        timing["init_duration"] = round(rag_init_duration, 3)
        logger.info(f"🚀 [MULTIMODAL] RAG initialized in {rag_init_duration:.3f}s")
        
        # Process query
        query_proc_start = time.time()
        result = run_async(rag.aquery_with_multimodal(
            query,
            multimodal_content=multimodal_content,
            mode=mode
        ))
        query_duration = time.time() - query_proc_start
        timing["query_duration"] = round(query_duration, 3)
        logger.info(f"🔍 [MULTIMODAL] Query processed in {query_duration:.3f}s")
        
        # Parse result
        parse_start = time.time()
        if isinstance(result, dict):
            answer = result.get('answer', str(result))
            sources = result.get('sources', [])
            confidence = result.get('confidence', 0.0)
        else:
            answer = str(result)
            sources = []
            confidence = 0.0
        parse_time = time.time() - parse_start
        timing["parse_duration"] = round(parse_time, 3)
        logger.info(f"📝 [MULTIMODAL] Result parsed in {parse_time:.3f}s")
        
        total_duration = time.time() - start_time
        timing["total_duration"] = round(total_duration, 3)
        logger.info(f"✅ [MULTIMODAL] Completed in {total_duration:.3f}s")
        
        return jsonify({
            "query": query,
            "answer": answer,
            "sources": sources,
            "confidence": confidence,
            "mode": mode,
            "multimodal_items": len(multimodal_content),
            "status": "completed",
            "timing": timing
        })
        
    except Exception as e:
        total_duration = time.time() - start_time
        timing["total_duration"] = round(total_duration, 3)
        logger.error(f"❌ [MULTIMODAL] Failed after {total_duration:.3f}s: {str(e)}")
        import traceback
        traceback.print_exc()
        
        return jsonify({
            "error": str(e),
            "status": "error",
            "timing": timing
        }), 500

# ============================================================================
# EFS ANALYSIS
# ============================================================================

@app.route('/analyze_efs', methods=['GET'])
def analyze_efs():
    """Analyze EFS contents"""
    start_time = time.time()
    logger.info("📊 [EFS_ANALYSIS] Starting...")
    timing = {}
    
    try:
        config_start = time.time()
        efs_path = os.environ.get('EFS_MOUNT_PATH', '/mnt/efs')
        rag_output_dir = os.environ.get('RAG_OUTPUT_DIR', '/mnt/efs/rag_output')
        config_time = time.time() - config_start
        timing["config_load"] = round(config_time, 3)
        logger.info(f"⚙️ [EFS_ANALYSIS] Config loaded in {config_time:.3f}s")
        
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
            total_time = time.time() - start_time
            timing["total_duration"] = round(total_time, 3)
            return jsonify({
                'error': f'EFS path {efs_path} not found',
                'analysis': analysis,
                "timing": timing
            }), 404
        
        # Walk through EFS
        walk_start = time.time()
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
        
        walk_time = time.time() - walk_start
        timing["efs_walk"] = round(walk_time, 3)
        logger.info(f"🚶 [EFS_ANALYSIS] EFS walked in {walk_time:.3f}s")
        
        # Sample chunks
        sample_start = time.time()
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
        sample_time = time.time() - sample_start
        timing["sample_chunks"] = round(sample_time, 3)
        logger.info(f"🔍 [EFS_ANALYSIS] Chunks sampled in {sample_time:.3f}s")
        
        total_duration = time.time() - start_time
        timing["total_duration"] = round(total_duration, 3)
        logger.info(f"✅ [EFS_ANALYSIS] Completed in {total_duration:.3f}s")
        
        return jsonify({
            'status': 'success',
            'analysis': analysis,
            "timing": timing
        })
        
    except Exception as e:
        total_duration = time.time() - start_time
        timing["total_duration"] = round(total_duration, 3)
        logger.error(f"❌ [EFS_ANALYSIS] Failed after {total_duration:.3f}s: {str(e)}")
        return jsonify({'error': str(e), "timing": timing}), 500

@app.route('/get_chunks', methods=['GET'])
def get_chunks():
    """Get full content of all chunks"""
    start_time = time.time()
    logger.info("📂 [CHUNKS] Get chunks started...")
    timing = {}
    
    try:
        config_start = time.time()
        rag_output_dir = os.environ.get('RAG_OUTPUT_DIR', '/mnt/efs/rag_output')
        config_time = time.time() - config_start
        timing["config_load"] = round(config_time, 3)
        logger.info(f"⚙️ [CHUNKS] Config loaded in {config_time:.3f}s")
        
        chunks_data = {
            'text_chunks': {},
            'entity_chunks': {},
            'relation_chunks': {},
            'vdb_chunks': {},
            'total_chunks': 0
        }
        
        # Read various chunk files
        read_start = time.time()
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
        
        read_time = time.time() - read_start
        timing["file_reading"] = round(read_time, 3)
        logger.info(f"📖 [CHUNKS] Files read in {read_time:.3f}s")
        
        total_duration = time.time() - start_time
        timing["total_duration"] = round(total_duration, 3)
        logger.info(f"✅ [CHUNKS] Completed in {total_duration:.3f}s")
        
        return jsonify({
            'status': 'success',
            'chunks': chunks_data,
            "timing": timing
        })
        
    except Exception as e:
        total_duration = time.time() - start_time
        timing["total_duration"] = round(total_duration, 3)
        logger.error(f"❌ [CHUNKS] Failed after {total_duration:.3f}s: {str(e)}")
        return jsonify({'error': str(e), "timing": timing}), 500

@app.route('/test_embedding', methods=['POST'])
def test_embedding():
    """Test the embedding function directly for debugging"""
    start_time = time.time()
    logger.info("🧪 [TEST_EMBED] Test embedding started...")
    timing = {}
    
    try:
        data = request.get_json()
        test_texts = data.get('texts', ['This is a test sentence.'])
        
        logger.info(f"🧪 [TEST_EMBED] Testing embedding with {len(test_texts)} text(s)")
        
        # Get embedding function
        func_start = time.time()
        embedding_func = get_embedding_func()
        func_time = time.time() - func_start
        timing["get_func"] = round(func_time, 3)
        logger.info(f"📊 [TEST_EMBED] Embedding func retrieved in {func_time:.3f}s")
        
        # Test the embedding - func returns a coroutine
        embed_start = time.time()
        result = run_async(embedding_func.func(test_texts))
        embed_time = time.time() - embed_start
        timing["embedding"] = round(embed_time, 3)
        logger.info(f"✅ [TEST_EMBED] Embedding tested in {embed_time:.3f}s")
        
        total_duration = time.time() - start_time
        timing["total_duration"] = round(total_duration, 3)
        logger.info(f"✅ [TEST_EMBED] Completed in {total_duration:.3f}s")
        
        return jsonify({
            'status': 'success',
            'input_texts': test_texts,
            'embedding_dim': len(result[0]) if result and len(result) > 0 else 0,
            'num_embeddings': len(result) if result else 0,
            'message': 'Embedding function working correctly',
            "timing": timing
        })
        
    except Exception as e:
        total_duration = time.time() - start_time
        timing["total_duration"] = round(total_duration, 3)
        logger.error(f"❌ [TEST_EMBED] Failed after {total_duration:.3f}s: {str(e)}")
        import traceback
        return jsonify({
            'error': str(e),
            'traceback': traceback.format_exc(),
            "timing": timing
        }), 500

@app.route('/analyze_efs_content', methods=['GET'])
def analyze_efs_content():
    """Download and return content of specific EFS file"""
    start_time = time.time()
    logger.info("📊 [EFS_CONTENT] Analyze EFS content started...")
    timing = {}
    
    try:
        filename = request.args.get('filename')
        if not filename:
            total_time = time.time() - start_time
            timing["total_duration"] = round(total_time, 3)
            return jsonify({
                'error': 'filename parameter required',
                "timing": timing
            }), 400
        
        config_start = time.time()
        efs_path = os.environ.get('EFS_MOUNT_PATH', '/mnt/efs')
        config_time = time.time() - config_start
        timing["config_load"] = round(config_time, 3)
        logger.info(f"⚙️ [EFS_CONTENT] Config loaded in {config_time:.3f}s")
        
        # Search for file
        search_start = time.time()
        file_path = None
        for root, dirs, files in os.walk(efs_path):
            if filename in files:
                file_path = os.path.join(root, filename)
                break
        
        search_time = time.time() - search_start
        timing["file_search"] = round(search_time, 3)
        logger.info(f"🔍 [EFS_CONTENT] File searched in {search_time:.3f}s")
        
        if not file_path:
            total_time = time.time() - start_time
            timing["total_duration"] = round(total_time, 3)
            return jsonify({'error': f'File not found: {filename}', "timing": timing}), 404
        
        # Read file
        read_start = time.time()
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
        
        read_time = time.time() - read_start
        timing["file_reading"] = round(read_time, 3)
        logger.info(f"📖 [EFS_CONTENT] File read in {read_time:.3f}s")
        
        total_duration = time.time() - start_time
        timing["total_duration"] = round(total_duration, 3)
        logger.info(f"✅ [EFS_CONTENT] Completed in {total_duration:.3f}s")
        
        return jsonify({
            'status': 'success',
            'filename': filename,
            'path': file_path,
            'content': file_content,
            "timing": timing
        })
        
    except Exception as e:
        total_duration = time.time() - start_time
        timing["total_duration"] = round(total_duration, 3)
        logger.error(f"❌ [EFS_CONTENT] Failed after {total_duration:.3f}s: {str(e)}")
        return jsonify({'error': str(e), "timing": timing}), 500

@app.route('/delete_all_data', methods=['POST'])
def delete_all_data():
    """Delete all generated data files from EFS (logs, md, chunk jsons, graphs, embeddings, etc.)"""
    start_time = time.time()
    logger.info("🗑️ [DELETE] Starting cleanup of all EFS data...")
    timing = {}
    
    try:
        config = get_rag_config()
        efs_path = config.working_dir
        
        if not os.path.exists(efs_path):
            total_duration = time.time() - start_time
            timing["total_duration"] = round(total_duration, 3)
            logger.warning(f"⚠️ [DELETE] EFS path does not exist: {efs_path}")
            return jsonify({
                'status': 'success',
                'message': 'EFS path does not exist - nothing to delete',
                'deleted_files': 0,
                'deleted_directories': 0,
                'timing': timing
            })
        
        deleted_files = 0
        deleted_directories = 0
        
        # Walk through all files and directories in EFS
        for root, dirs, files in os.walk(efs_path, topdown=False):
            # Delete all files
            for file in files:
                file_path = os.path.join(root, file)
                try:
                    os.remove(file_path)
                    deleted_files += 1
                    logger.info(f"🗑️ [DELETE] Deleted file: {file_path}")
                except Exception as e:
                    logger.error(f"❌ [DELETE] Failed to delete file {file_path}: {str(e)}")
            
            # Delete empty directories (except root)
            for dir_name in dirs:
                dir_path = os.path.join(root, dir_name)
                try:
                    if os.path.exists(dir_path) and not os.listdir(dir_path):
                        os.rmdir(dir_path)
                        deleted_directories += 1
                        logger.info(f"🗑️ [DELETE] Deleted directory: {dir_path}")
                except Exception as e:
                    logger.error(f"❌ [DELETE] Failed to delete directory {dir_path}: {str(e)}")
        
        # Clear any cached RAG instance to force reinitialization
        global _rag_instance
        _rag_instance = None
        logger.info("🔄 [DELETE] Cleared cached RAG instance")
        
        total_duration = time.time() - start_time
        timing["total_duration"] = round(total_duration, 3)
        logger.info(f"✅ [DELETE] Cleanup completed in {total_duration:.3f}s")
        logger.info(f"📊 [DELETE] Deleted {deleted_files} files and {deleted_directories} directories")
        
        return jsonify({
            'status': 'success',
            'message': 'All EFS data deleted successfully',
            'deleted_files': deleted_files,
            'deleted_directories': deleted_directories,
            'efs_path': efs_path,
            'timing': timing
        })
        
    except Exception as e:
        total_duration = time.time() - start_time
        timing["total_duration"] = round(total_duration, 3)
        logger.error(f"❌ [DELETE] Failed after {total_duration:.3f}s: {str(e)}")
        return jsonify({'error': str(e), "timing": timing}), 500

# ============================================================================
# SERVER STARTUP
# ============================================================================

def start_server():
    """Start Flask server"""
    start_time = time.time()
    port = int(os.environ.get('PORT', 8000))
    
    logger.info("🚀 [SERVER] Starting RAG-Anything Server...")
    logger.info(f"🔌 [SERVER] Port: {port}")
    logger.info(f"📂 [SERVER] Working Dir: {os.environ.get('OUTPUT_DIR', '/rag-output/')}")
    logger.info(f"🔧 [SERVER] Parser: {os.environ.get('PARSER', 'docling')}")
    logger.info(f"⏱️ [SERVER] Async Timeout: {os.environ.get('ASYNC_TIMEOUT', '300')}s")
    
    app.run(
        host='0.0.0.0',
        port=port,
        debug=False,
        threaded=True,
        use_reloader=False
    )
    total_time = time.time() - start_time
    logger.info(f"🚀 [SERVER] Server started in {total_time:.3f}s")

if __name__ == '__main__':
    start_server()