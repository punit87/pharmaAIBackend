#!/usr/bin/env python3
"""
RAG-Anything Server - Optimized for ECS Tasks
- Persistent event loop for efficient async operations
- Lazy initialization to reduce cold start time
- Proper resource cleanup
- Memory-efficient caching
- Fixed async handling matching RAG-Anything reference implementation
- Custom LLM-based chunking using gpt-4o-mini for tables, lists, bullets, paragraphs, sections, and regular text
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
from lightrag import LightRAG
from lightrag.llm.openai import openai_complete_if_cache, openai_embed
from lightrag.utils import EmbeddingFunc
from lightrag.kg.shared_storage import initialize_pipeline_status
from docling.document_converter import DocumentConverter

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
# EVENT LOOP MANAGEMENT
# ============================================================================

def get_event_loop():
    """Get or create persistent event loop for async operations"""
    global _event_loop
    start_time = time.time()
    logger.info("🔄 [EVENT_LOOP] Getting event loop...")
    
    if _event_loop is None or _event_loop.is_closed():
        logger.info("🔄 [EVENT_LOOP] Creating new event loop...")
        _event_loop = asyncio.new_event_loop()
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
# ACTIVITY TRACKING
# ============================================================================

def update_activity():
    """Update activity timestamp for monitoring"""
    pass

# ============================================================================
# RAG CONFIGURATION
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
    
    # Normalize the working directory path to avoid trailing slash issues
    working_dir = os.environ.get('OUTPUT_DIR', '/mnt/efs/rag_output')
    working_dir = os.path.normpath(working_dir)  # Remove trailing slashes and normalize path
    
    # Validate and log path consistency
    efs_mount_path = os.environ.get('EFS_MOUNT_PATH', '/mnt/efs')
    rag_output_dir_env = os.environ.get('RAG_OUTPUT_DIR', '/mnt/efs/rag_output')
    rag_output_dir_env = os.path.normpath(rag_output_dir_env)
    
    logger.info(f"⚙️ [CONFIG] Path validation:")
    logger.info(f"⚙️ [CONFIG]   EFS_MOUNT_PATH: {efs_mount_path}")
    logger.info(f"⚙️ [CONFIG]   RAG_OUTPUT_DIR: {rag_output_dir_env}")
    logger.info(f"⚙️ [CONFIG]   OUTPUT_DIR (working_dir): {working_dir}")
    
    # Check for path consistency
    if working_dir != rag_output_dir_env:
        logger.warning(f"⚠️ [CONFIG] PATH MISMATCH DETECTED!")
        logger.warning(f"⚠️ [CONFIG]   working_dir: {working_dir}")
        logger.warning(f"⚠️ [CONFIG]   RAG_OUTPUT_DIR: {rag_output_dir_env}")
        logger.warning(f"⚠️ [CONFIG] This may cause issues with finding existing chunks!")
    
    # Check if paths exist and are accessible
    if os.path.exists(working_dir):
        logger.info(f"✅ [CONFIG] Working directory exists: {working_dir}")
        try:
            files_count = len(os.listdir(working_dir))
            logger.info(f"📁 [CONFIG] Working directory contains {files_count} items")
        except Exception as e:
            logger.warning(f"⚠️ [CONFIG] Cannot list working directory contents: {str(e)}")
    else:
        logger.warning(f"⚠️ [CONFIG] Working directory does not exist: {working_dir}")
    
    config = RAGAnythingConfig(
        working_dir=working_dir,  # Normalized path without trailing slash
        parser=os.environ.get('PARSER', 'docling'),  # Using Docling parser
        parse_method=os.environ.get('PARSE_METHOD', 'ocr'),  # Using OCR for document parsing
        enable_image_processing=False,  # Disable VLM processing to avoid NoneType error
        enable_table_processing=False,  # Disable built-in table chunking
        enable_equation_processing=False  # Disable equation processing to avoid VLM issues
    )
    
    # Ensure working directory exists
    os.makedirs(config.working_dir, exist_ok=True)
    
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
    """Create LLM model function - SYNCHRONOUS wrapper that returns coroutine"""
    start_time = time.time()
    logger.info("🤖 [LLM] Creating LLM model function...")
    
    config = get_api_config()
    
    def llm_func(prompt, system_prompt=None, history_messages=[], **kwargs):
        """Synchronous function that returns a coroutine"""
        # Safeguard: Ensure prompt is never None - trigger build
        if prompt is None:
            prompt = ""
            logger.warning("⚠️ [LLM] Prompt was None, converted to empty string")
        
        # Additional safeguard: Ensure prompt is a string
        if not isinstance(prompt, str):
            prompt = str(prompt) if prompt is not None else ""
            logger.warning(f"⚠️ [LLM] Prompt was {type(prompt)}, converted to string")
        
        llm_start_time = time.time()
        logger.info(f"🤖 [LLM] Starting LLM completion...")
        logger.info(f"🤖 [LLM] Prompt length: {len(prompt)} characters")
        
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
    
    exec_time = time.time() - start_time
    logger.info(f"🤖 [LLM] LLM model function created in {exec_time:.3f}s")
    return llm_func

def get_vision_model_func(llm_func):
    """Create vision model function - SYNCHRONOUS wrapper that returns coroutine"""
    start_time = time.time()
    config = get_api_config()
    
    def vision_func(prompt, system_prompt=None, history_messages=[], 
                   image_data=None, messages=None, **kwargs):
        """Synchronous function that returns a coroutine"""
        # Safeguard: Ensure prompt is never None
        if prompt is None:
            prompt = ""
            logger.warning("⚠️ [VISION] Prompt was None, converted to empty string")
        
        # Additional safeguard: Ensure prompt is a string
        if not isinstance(prompt, str):
            prompt = str(prompt) if prompt is not None else ""
            logger.warning(f"⚠️ [VISION] Prompt was {type(prompt)}, converted to string")
        
        if messages:
            return openai_complete_if_cache(
                "gpt-4o", "", system_prompt=None, history_messages=[],
                messages=messages, api_key=config['api_key'], 
                base_url=config['base_url'], **kwargs
            )
        elif image_data:
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
        else:
            return llm_func(prompt, system_prompt, history_messages, **kwargs)
    
    exec_time = time.time() - start_time
    logger.info(f"🤖 [VISION] Vision model function created in {exec_time:.3f}s")
    return vision_func

def get_embedding_func():
    """Create embedding function - handles both sync and async contexts"""
    start_time = time.time()
    config = get_api_config()
    
    async def safe_embed_async(texts):
        """Async embedding function that properly formats input for OpenAI API"""
        embed_start = time.time()
        try:
            if isinstance(texts, str):
                input_texts = [texts.strip()]
            elif isinstance(texts, list):
                input_texts = [str(t).strip() for t in texts if t is not None and str(t).strip()]
                if not input_texts:
                    raise ValueError("No valid text inputs provided for embedding")
            else:
                logger.warning(f"⚠️ [EMBEDDING] Unexpected input type: {type(texts)}, converting to string")
                input_texts = [str(texts).strip()]
            
            if not input_texts:
                raise ValueError(f"Empty text input for embedding: {texts}")
            
            # Check if any text is non-empty (avoid numpy array comparison issues)
            has_valid_text = False
            for text in input_texts:
                if text and str(text).strip():
                    has_valid_text = True
                    break
            
            if not has_valid_text:
                raise ValueError(f"No valid non-empty text input for embedding: {texts}")
            
            logger.info(f"📊 [EMBEDDING] Processing {len(input_texts)} text(s)")
            logger.debug(f"📊 [EMBEDDING] First text preview: {input_texts[0][:100]}...")
            
            result = await openai_embed(
                texts=input_texts,
                model="text-embedding-ada-002",
                api_key=config['api_key'],
                base_url=config['base_url'],
            )
            
            embed_time = time.time() - embed_start
            logger.info(f"✅ [EMBEDDING] Successfully generated {len(result)} embedding(s) in {embed_time:.3f}s")
            
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
        """Synchronous wrapper that returns the coroutine"""
        return safe_embed_async(texts)
    
    exec_time = time.time() - start_time
    logger.info(f"📊 [EMBEDDING] Embedding function created in {exec_time:.3f}s")
    return EmbeddingFunc(
        embedding_dim=1536,
        max_token_size=8191,
        func=safe_embed_sync,
    )

# ============================================================================
# CUSTOM LLM CHUNKING
# ============================================================================

async def custom_llm_chunking(markdown_content, doc_id, llm_func):
    """Custom LLM-based chunking for markdown content using gpt-4o-mini"""
    start_time = time.time()
    logger.info("🔪 [CHUNKING] Starting custom LLM chunking...")
    
    try:
        # System prompt to guide LLM in chunking - LightRAG compatible format
        system_prompt = """
You are an expert document parser. Your task is to analyze markdown content and chunk it into meaningful segments compatible with LightRAG format. Return a JSON list of chunks with the following structure that matches LightRAG's expected format:

{
  "chunks": [
    {
      "type": "text",
      "content": "string content of the chunk",
      "metadata": {
        "doc_id": "string",
        "chunk_id": "string (unique within doc)",
        "page_idx": int,
        "section_title": "string (if applicable)",
        "chunk_type": "paragraph" | "table" | "list" | "heading" | "text"
      }
    }
  ]
}

IMPORTANT FORMAT REQUIREMENTS:
- Use "type": "text" for all chunks (LightRAG standard)
- Keep content concise but meaningful (max 500 characters per chunk)
- Ensure each chunk is self-contained and searchable
- For tables: extract key information as readable text
- For lists: convert to paragraph format
- For headings: include as section_title in metadata
- Preserve context and meaning in each chunk
"""
        # Split markdown into manageable chunks to avoid token limits
        max_chunk_size = 3000
        markdown_chunks = [markdown_content[i:i+max_chunk_size] for i in range(0, len(markdown_content), max_chunk_size)]
        all_chunks = []
        
        for chunk_idx, markdown_part in enumerate(markdown_chunks):
            prompt = f"Analyze the following markdown content and chunk it according to the instructions:\n\n{markdown_part}"
            logger.info(f"🔪 [CHUNKING] Processing markdown chunk {chunk_idx+1}/{len(markdown_chunks)}")
            
            # Call LLM
            response = await llm_func(
                prompt=prompt,
                system_prompt=system_prompt,
                response_format={"type": "json_object"}
            )
            
            # Parse response
            try:
                # Handle different response formats
                if isinstance(response, dict):
                    if 'response' in response:
                        response_text = response['response']
                    elif 'choices' in response:
                        response_text = response['choices'][0]['message']['content']
                    else:
                        response_text = str(response)
                else:
                    response_text = str(response)
                
                result = json.loads(response_text)
                chunks = result.get('chunks', [])
                
                # Validate and process chunks in LightRAG format
                for chunk in chunks:
                    if not isinstance(chunk, dict):
                        logger.warning(f"⚠️ [CHUNKING] Skipping invalid chunk: {type(chunk)}")
                        continue
                    
                    # Ensure required fields exist
                    if 'content' not in chunk:
                        logger.warning(f"⚠️ [CHUNKING] Skipping chunk without content")
                        continue
                    
                    # Ensure metadata exists
                    if 'metadata' not in chunk:
                        chunk['metadata'] = {}
                    
                    # Set LightRAG-compatible fields
                    chunk['type'] = 'text'  # LightRAG standard type
                    chunk['metadata']['doc_id'] = doc_id
                    chunk['metadata']['page_idx'] = chunk_idx  # Approximate page index
                    chunk['metadata']['chunk_id'] = f"{doc_id}_{chunk_idx}_{len(all_chunks)}"
                    
                    # Ensure chunk_type is set
                    if 'chunk_type' not in chunk['metadata']:
                        chunk['metadata']['chunk_type'] = 'text'
                    
                    all_chunks.append(chunk)
            except Exception as e:
                logger.error(f"❌ [CHUNKING] Failed to parse LLM response: {str(e)}")
                continue
        
        exec_time = time.time() - start_time
        logger.info(f"✅ [CHUNKING] Custom chunking completed in {exec_time:.3f}s with {len(all_chunks)} chunks")
        return all_chunks
    
    except Exception as e:
        exec_time = time.time() - start_time
        logger.error(f"❌ [CHUNKING] Custom chunking failed after {exec_time:.3f}s: {str(e)}")
        raise e

# ============================================================================
# LAZY RAG INITIALIZATION
# ============================================================================

def get_rag_instance():
    """Get or create singleton RAG instance with proper thread safety and existing data loading"""
    global _rag_instance
    start_time = time.time()
    logger.info("🚀 [RAG_INIT] Getting RAG instance...")
    
    if _rag_instance is not None:
        logger.info(f"🚀 [RAG_INIT] Using cached RAG instance in {time.time() - start_time:.3f}s")
        return _rag_instance
    
    with _rag_lock:
        if _rag_instance is None:
            logger.info("🚀 [RAG_INIT] Creating new RAG-Anything singleton...")
            
            init_start = time.time()
            try:
                config = get_rag_config()
                llm_func = get_llm_model_func()
                vision_func = get_vision_model_func(llm_func)
                embedding_func = get_embedding_func()
                
                # Create RAGAnything instance following official repo pattern
                logger.info("🚀 [RAG_INIT] Creating RAG-Anything instance with Docling parser...")
                
                _rag_instance = RAGAnything(
                    config=config,
                    llm_model_func=llm_func,
                    vision_model_func=vision_func,
                    embedding_func=embedding_func,
                )
                
                # Check if existing LightRAG data exists and try to load it
                lightrag_working_dir = config.working_dir
                logger.info(f"🚀 [RAG_INIT] Checking for existing LightRAG data in: {lightrag_working_dir}")
                
                # Check if directory exists and has files
                if os.path.exists(lightrag_working_dir) and os.listdir(lightrag_working_dir):
                    logger.info("🚀 [RAG_INIT] Found existing LightRAG data, attempting to load...")
                    
                    try:
                        # Try to initialize the underlying LightRAG instance
                        # This should automatically load existing data
                        logger.info("🚀 [RAG_INIT] Checking LightRAG instance accessibility...")
                        
                        # Check if RAGAnything instance has lightrag attribute
                        if not hasattr(_rag_instance, 'lightrag'):
                            logger.warning("🚀 [RAG_INIT] RAGAnything instance has no 'lightrag' attribute")
                            logger.info("🚀 [RAG_INIT] Creating LightRAG instance...")
                            
                            # Create LightRAG instance manually
                            from lightrag import LightRAG
                            
                            lightrag_instance = LightRAG(
                                working_dir=lightrag_working_dir,
                                llm_model_func=llm_func,
                                embedding_func=embedding_func
                            )
                            
                            # Set the LightRAG instance on the RAG-Anything instance
                            _rag_instance.lightrag = lightrag_instance
                            logger.info("🚀 [RAG_INIT] LightRAG instance created successfully")
                            
                        elif _rag_instance.lightrag is None:
                            logger.warning("🚀 [RAG_INIT] LightRAG instance is None")
                            logger.info("🚀 [RAG_INIT] Creating LightRAG instance...")
                            
                            # Create LightRAG instance manually
                            from lightrag import LightRAG
                            
                            lightrag_instance = LightRAG(
                                working_dir=lightrag_working_dir,
                                llm_model_func=llm_func,
                                embedding_func=embedding_func
                            )
                            
                            # Set the LightRAG instance on the RAG-Anything instance
                            _rag_instance.lightrag = lightrag_instance
                            logger.info("🚀 [RAG_INIT] LightRAG instance created successfully")
                        
                        # Now try to load existing data
                        logger.info("🚀 [RAG_INIT] LightRAG instance ready, attempting to load existing data...")
                        
                        # Check if initialize_storages method exists
                        if not hasattr(_rag_instance.lightrag, 'initialize_storages'):
                            logger.warning("🚀 [RAG_INIT] LightRAG instance has no 'initialize_storages' method")
                            logger.info("🚀 [RAG_INIT] Skipping data loading - using fresh instance")
                        else:
                            logger.info("🚀 [RAG_INIT] Calling initialize_storages()...")
                            run_async(_rag_instance.lightrag.initialize_storages())
                            
                            logger.info("🚀 [RAG_INIT] Calling initialize_pipeline_status()...")
                            run_async(initialize_pipeline_status())
                            
                            logger.info("🚀 [RAG_INIT] Existing LightRAG data loaded successfully")
                    except Exception as e:
                        logger.warning(f"🚀 [RAG_INIT] Failed to load existing data: {str(e)}")
                        logger.info("🚀 [RAG_INIT] Continuing with fresh instance")
                        import traceback
                        logger.debug(f"🚀 [RAG_INIT] Traceback: {traceback.format_exc()}")
                else:
                    logger.info("🚀 [RAG_INIT] No existing data found, using fresh instance")
                
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
    """Process document from S3 with custom LLM chunking"""
    start_time = time.time()
    logger.info("📄 [PROCESS] Document processing started...")
    temp_file_path = None
    timing = {}
    
    try:
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
        s3_bucket = data.get('bucket') or data.get('s3_bucket')
        s3_key = data.get('key') or data.get('s3_key')
        
        if not s3_bucket or not s3_key:
            total_time = time.time() - start_time
            timing["total_duration"] = round(total_time, 3)
            return jsonify({"error": "Missing bucket or key", "timing": timing}), 400
        
        logger.info(f"📦 [PROCESS] s3://{s3_bucket}/{s3_key}")
        
        # Download from S3
        download_start = time.time()
        s3_client = boto3.client('s3')
        # Create safe temp file path
        safe_filename = os.path.basename(s3_key).replace('/', '_').replace('\\', '_')
        temp_file_path = f"/tmp/{safe_filename}"
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
        
        # Parse document to markdown
        parse_start = time.time()
        parser = os.environ.get('PARSER', 'docling')
        parse_method = os.environ.get('PARSE_METHOD', 'ocr')
        logger.info(f"🔍 [PROCESS] Parsing with {parser} ({parse_method})")
        
        # Use RAG-Anything's parser to get markdown
        parse_result = run_async(rag.parse_document(temp_file_path, parse_method=parse_method))
        
        # Debug: Log the type and content of parse_result
        logger.info(f"🔍 [PROCESS] parse_result type: {type(parse_result)}")
        logger.info(f"🔍 [PROCESS] parse_result content: {str(parse_result)[:200]}...")
        
        # Handle different return types from parse_document
        if isinstance(parse_result, tuple):
            # If it's a tuple, extract the first element (usually the document object)
            doc_obj = parse_result[0]
            if hasattr(doc_obj, 'to_markdown'):
                markdown_content = doc_obj.to_markdown()
            elif hasattr(doc_obj, 'markdown'):
                markdown_content = doc_obj.markdown
            else:
                markdown_content = str(doc_obj)
        elif isinstance(parse_result, dict):
            markdown_content = parse_result.get('markdown', '')
        else:
            markdown_content = str(parse_result)
        parse_duration = time.time() - parse_start
        timing["parse_duration"] = round(parse_duration, 3)
        logger.info(f"🔍 [PROCESS] Document parsed to markdown in {parse_duration:.3f}s")
        
        # Custom LLM chunking
        chunk_start = time.time()
        logger.info("🔪 [PROCESS] Starting custom LLM chunking...")
        llm_func = get_llm_model_func()
        chunks = run_async(custom_llm_chunking(markdown_content, s3_key, llm_func))
        chunk_duration = time.time() - chunk_start
        timing["chunk_duration"] = round(chunk_duration, 3)
        logger.info(f"🔪 [PROCESS] Custom chunking produced {len(chunks)} chunks in {chunk_duration:.3f}s")
        
        # Insert chunks into RAG-Anything in LightRAG-compatible format
        insert_start = time.time()
        content_list = []
        for chunk in chunks:
            # Ensure LightRAG-compatible format
            content_item = {
                'content': chunk['content'],
                'metadata': chunk['metadata'],
                'type': chunk.get('type', 'text')  # Default to 'text' if not specified
            }
            content_list.append(content_item)
        
        run_async(rag.insert_content_list(content_list, doc_id=s3_key))
        insert_duration = time.time() - insert_start
        timing["insert_duration"] = round(insert_duration, 3)
        logger.info(f"📥 [PROCESS] Inserted {len(content_list)} LightRAG-compatible chunks in {insert_duration:.3f}s")
        
        total_duration = time.time() - start_time
        timing["total_duration"] = round(total_duration, 3)
        logger.info(f"✅ [PROCESS] Completed in {total_duration:.3f}s")
        
        return jsonify({
            "status": "success",
            "bucket": s3_bucket,
            "key": s3_key,
            "message": f"Document processed with {len(chunks)} custom chunks",
            "timing": timing
        })
    
    except Exception as e:
        total_duration = time.time() - start_time
        timing["total_duration"] = round(total_duration, 3)
        logger.error(f"❌ [PROCESS] Failed after {total_duration:.3f}s: {str(e)}")
        import traceback
        traceback.print_exc()
        
        return jsonify({
            "error": str(e),
            "timing": timing
        }), 500
    
    finally:
        if temp_file_path and os.path.exists(temp_file_path):
            try:
                os.remove(temp_file_path)
                logger.info(f"🗑️ [PROCESS] Cleaned up temp file: {temp_file_path}")
            except Exception as e:
                logger.warning(f"⚠️ [PROCESS] Failed to clean up temp file: {str(e)}")

# ============================================================================
# QUERY ENDPOINT
# ============================================================================

@app.route('/query', methods=['POST'])
def query():
    """Query the RAG knowledge base"""
    start_time = time.time()
    logger.info("🔍 [QUERY] Query started...")
    timing = {}
    
    try:
        data = request.get_json()
        query = data.get('query')
        mode = data.get('mode', 'hybrid')  # Default to hybrid mode for full RAG functionality
        
        if not query:
            total_duration = time.time() - start_time
            timing["total_duration"] = round(total_duration, 3)
            return jsonify({"error": "Missing query", "timing": timing}), 400
        
        rag = get_rag_instance()
        
        query_proc_start = time.time()
        try:
            result = run_async(rag.aquery(query, mode=mode))
        except Exception as e:
            logger.error(f"❌ [QUERY] Query processing failed: {str(e)}")
            # If VLM processing fails, try with a simpler mode
            if "expected string or bytes-like object, got 'NoneType'" in str(e):
                logger.info("🔄 [QUERY] Retrying with local mode...")
                try:
                    result = run_async(rag.aquery(query, mode="local"))
                except Exception as retry_e:
                    logger.error(f"❌ [QUERY] Retry also failed: {str(retry_e)}")
                    result = None
            else:
                result = None
        
        query_duration = time.time() - query_proc_start
        timing["query_duration"] = round(query_duration, 3)
        logger.info(f"🔍 [QUERY] Query processed in {query_duration:.3f}s")
        
        parse_start = time.time()
        if result is None:
            answer = "No results found for the query."
            sources = []
            confidence = 0.0
            logger.warning("⚠️ [QUERY] Query returned None result")
        elif isinstance(result, dict):
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
# MULTIMODAL QUERY ENDPOINT
# ============================================================================

@app.route('/query_multimodal', methods=['POST'])
def query_multimodal():
    """Query the RAG knowledge base with multimodal content"""
    start_time = time.time()
    logger.info("🔍 [MULTIMODAL] Multimodal query started...")
    timing = {}
    
    try:
        data = request.get_json()
        query = data.get('query')
        multimodal_content = data.get('multimodal_content', [])
        mode = data.get('mode', 'hybrid')
        
        if not query:
            total_duration = time.time() - start_time
            timing["total_duration"] = round(total_duration, 3)
            return jsonify({"error": "Missing query", "timing": timing}), 400
        
        rag = get_rag_instance()
        
        query_proc_start = time.time()
        result = run_async(rag.aquery_with_multimodal(
            query,
            multimodal_content=multimodal_content,
            mode=mode
        ))
        query_duration = time.time() - query_proc_start
        timing["query_duration"] = round(query_duration, 3)
        logger.info(f"🔍 [MULTIMODAL] Query processed in {query_duration:.3f}s")
        
        parse_start = time.time()
        if result is None:
            answer = "No results found for the query."
            sources = []
            confidence = 0.0
            logger.warning("⚠️ [MULTIMODAL] Query returned None result")
        elif isinstance(result, dict):
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
        rag_output_dir = os.path.normpath(rag_output_dir)  # Normalize path to match working_dir
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
    """Get full content of all chunks from EFS"""
    start_time = time.time()
    logger.info("📂 [CHUNKS] Get chunks started...")
    timing = {}
    
    try:
        config_start = time.time()
        rag_output_dir = os.environ.get('RAG_OUTPUT_DIR', '/mnt/efs/rag_output')
        rag_output_dir = os.path.normpath(rag_output_dir)  # Normalize path to match working_dir
        
        # Get working directory from RAG config for comparison
        try:
            rag_config = get_rag_config()
            working_dir = rag_config.working_dir
            logger.info(f"⚙️ [CHUNKS] Path comparison:")
            logger.info(f"⚙️ [CHUNKS]   get_chunks using: {rag_output_dir}")
            logger.info(f"⚙️ [CHUNKS]   RAG working_dir: {working_dir}")
            
            if rag_output_dir != working_dir:
                logger.warning(f"⚠️ [CHUNKS] PATH MISMATCH DETECTED!")
                logger.warning(f"⚠️ [CHUNKS]   get_chunks path: {rag_output_dir}")
                logger.warning(f"⚠️ [CHUNKS]   RAG working_dir: {working_dir}")
                logger.warning(f"⚠️ [CHUNKS] This may cause chunks not to be found!")
        except Exception as e:
            logger.warning(f"⚠️ [CHUNKS] Could not compare paths: {str(e)}")
        
        config_time = time.time() - config_start
        timing["config_load"] = round(config_time, 3)
        logger.info(f"⚙️ [CHUNKS] Config loaded in {config_time:.3f}s")
        
        chunks_data = {
            'documents': {},
            'total_chunks': 0,
            'total_documents': 0
        }
        
        # First, try the legacy chunk files in root directory
        legacy_chunk_files = {
            'text_chunks': f"{rag_output_dir}/kv_store_text_chunks.json",
            'entity_chunks': f"{rag_output_dir}/kv_store_entity_chunks.json",
            'relation_chunks': f"{rag_output_dir}/kv_store_relation_chunks.json",
            'vdb_chunks': f"{rag_output_dir}/vdb_chunks.json"
        }
        
        legacy_found = False
        read_start = time.time()
        
        # Check for legacy files first
        for key, path in legacy_chunk_files.items():
            if os.path.exists(path):
                with open(path, 'r', encoding='utf-8') as f:
                    chunks_data[key] = json.load(f)
                    if key == 'text_chunks':
                        chunks_data['total_chunks'] += len(chunks_data[key])
                legacy_found = True
        
        # If no legacy files found, look for document-specific chunks and LightRAG files
        if not legacy_found and os.path.exists(rag_output_dir):
            logger.info(f"🔍 [CHUNKS] No legacy files found, searching for document-specific chunks and LightRAG files...")
            
            # First, scan the directory structure to understand what's actually there
            logger.info(f"🔍 [CHUNKS] Scanning directory structure in: {rag_output_dir}")
            try:
                for root, dirs, files in os.walk(rag_output_dir):
                    logger.info(f"📁 [CHUNKS] Directory: {root}")
                    logger.info(f"📁 [CHUNKS]   Subdirectories: {dirs}")
                    logger.info(f"📁 [CHUNKS]   Files: {files}")
                    if files:  # Only show first few files to avoid log spam
                        logger.info(f"📁 [CHUNKS]   Sample files: {files[:5]}")
            except Exception as e:
                logger.warning(f"⚠️ [CHUNKS] Failed to scan directory structure: {str(e)}")
            
            # Look for LightRAG-specific files in root directory
            lightrag_files = [
                'graph.json', 'graph.db', 'vector_store.json', 'doc_status.json',
                'kv_store_text_chunks.json', 'kv_store_entity_chunks.json', 
                'kv_store_relation_chunks.json', 'vdb_chunks.json'
            ]
            
            for lightrag_file in lightrag_files:
                file_path = os.path.join(rag_output_dir, lightrag_file)
                if os.path.exists(file_path):
                    try:
                        with open(file_path, 'r', encoding='utf-8') as f:
                            content = json.load(f)
                            chunks_data[f'lightrag_{lightrag_file.replace(".json", "").replace(".db", "")}'] = content
                            logger.info(f"📄 [CHUNKS] Found LightRAG file: {lightrag_file}")
                    except Exception as e:
                        logger.warning(f"⚠️ [CHUNKS] Failed to read LightRAG file {file_path}: {str(e)}")
            
            # Walk through all document directories
            for root, dirs, files in os.walk(rag_output_dir):
                for file in files:
                    if file.endswith('.json') or file.endswith('.md'):
                        file_path = os.path.join(root, file)
                        try:
                            with open(file_path, 'r', encoding='utf-8') as f:
                                if file.endswith('.json'):
                                    content = json.load(f)
                                else:  # .md files
                                    content = f.read()
                                
                                # Extract document ID from path
                                rel_path = os.path.relpath(file_path, rag_output_dir)
                                doc_id = rel_path.split('/')[0] if '/' in rel_path else 'unknown'
                                
                                if doc_id not in chunks_data['documents']:
                                    chunks_data['documents'][doc_id] = {
                                        'files': {},
                                        'total_chunks': 0
                                    }
                                
                                chunks_data['documents'][doc_id]['files'][file] = {
                                    'path': file_path,
                                    'size': len(str(content)),
                                    'content': content,
                                    'type': 'json' if file.endswith('.json') else 'markdown'
                                }
                                
                                # Count chunks if it's a structured chunk file
                                if file.endswith('.json'):
                                    if isinstance(content, list):
                                        chunks_data['documents'][doc_id]['total_chunks'] += len(content)
                                        chunks_data['total_chunks'] += len(content)
                                    elif isinstance(content, dict) and 'chunks' in content:
                                        chunks_data['documents'][doc_id]['total_chunks'] += len(content['chunks'])
                                        chunks_data['total_chunks'] += len(content['chunks'])
                                else:  # .md files
                                    # For markdown files, count lines as a rough chunk estimate
                                    lines = content.split('\n')
                                    non_empty_lines = [line for line in lines if line.strip()]
                                    chunks_data['documents'][doc_id]['total_chunks'] += len(non_empty_lines)
                                    chunks_data['total_chunks'] += len(non_empty_lines)
                                    
                        except Exception as e:
                            logger.warning(f"⚠️ [CHUNKS] Failed to read {file_path}: {str(e)}")
            
            chunks_data['total_documents'] = len(chunks_data['documents'])
        
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
        
        func_start = time.time()
        embedding_func = get_embedding_func()
        func_time = time.time() - func_start
        timing["get_func"] = round(func_time, 3)
        logger.info(f"📊 [TEST_EMBED] Embedding func retrieved in {func_time:.3f}s")
        
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
    """Delete all generated data files from EFS"""
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
        
        for root, dirs, files in os.walk(efs_path, topdown=False):
            for file in files:
                file_path = os.path.join(root, file)
                try:
                    os.remove(file_path)
                    deleted_files += 1
                    logger.info(f"🗑️ [DELETE] Deleted file: {file_path}")
                except Exception as e:
                    logger.error(f"❌ [DELETE] Failed to delete file {file_path}: {str(e)}")
            
            for dir_name in dirs:
                dir_path = os.path.join(root, dir_name)
                try:
                    if os.path.exists(dir_path) and not os.listdir(dir_path):
                        os.rmdir(dir_path)
                        deleted_directories += 1
                        logger.info(f"🗑️ [DELETE] Deleted directory: {dir_path}")
                except Exception as e:
                    logger.error(f"❌ [DELETE] Failed to delete directory {dir_path}: {str(e)}")
        
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