#!/usr/bin/env python3
"""
RAG-Anything Server - Complete RAG framework with document processing and querying
Based on https://github.com/HKUDS/RAG-Anything
"""
import os
import json
import boto3
import asyncio
import threading
import time
import requests
from typing import Dict, Any
from flask import Flask, request, jsonify
from raganything import RAGAnything

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

def get_environment_variables():
    """Get all required environment variables"""
    return {
        'neo4j_uri': os.environ.get('NEO4J_URI'),
        'neo4j_username': os.environ.get('NEO4J_USERNAME'),
        'neo4j_password': os.environ.get('NEO4J_PASSWORD'),
        'openai_api_key': os.environ.get('OPENAI_API_KEY'),
        'docling_url': os.environ.get('DOCLING_SERVICE_URL', 'http://localhost:8000')
    }

def initialize_rag_anything(env_vars):
    """Initialize RAG-Anything with environment variables"""
    return RAGAnything(
        neo4j_uri=env_vars['neo4j_uri'],
        neo4j_username=env_vars['neo4j_username'],
        neo4j_password=env_vars['neo4j_password'],
        openai_api_key=env_vars['openai_api_key'],
        docling_url=env_vars['docling_url']
    )

def create_error_response(error_msg, duration, query=None):
    """Create standardized error response"""
    base_response = {
        "error": error_msg,
        "timing": {"total_duration": duration, "error": str(error_msg)}
    }
    
    if query is not None:
        base_response.update({
            "query": query,
            "answer": f"Error processing query: {error_msg}",
            "sources": [],
            "confidence": 0.0,
            "status": "error"
        })
    
    return base_response

# Start the auto-stop timer
timer_thread = threading.Thread(target=auto_stop_timer, daemon=True)
timer_thread.start()

@app.route('/health', methods=['GET'])
def health():
    """Health check endpoint"""
    return jsonify({"status": "healthy", "service": "raganything"})

@app.route('/process', methods=['POST'])
def process_document():
    """Process document using RAG-Anything with Docling for parsing"""
    start_time = time.time()
    print(f"🔄 [RAG] Starting document processing at {time.strftime('%Y-%m-%d %H:%M:%S.%f')[:-3]}")
    
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
        
        # Get environment variables
        env_vars = get_environment_variables()
        
        # Download file from S3
        download_start = time.time()
        s3_client = boto3.client('s3')
        temp_file_path = f"/tmp/{os.path.basename(s3_key)}"
        s3_client.download_file(s3_bucket, s3_key, temp_file_path)
        download_duration = time.time() - download_start
        print(f"📥 [RAG] S3 download completed in {download_duration:.3f}s")
        
        # Initialize RAG-Anything with Docling parser
        init_start = time.time()
        rag = initialize_rag_anything(env_vars)
        init_duration = time.time() - init_start
        print(f"🚀 [RAG] RAG-Anything initialization completed in {init_duration:.3f}s")
        
        # Process document using RAG-Anything with Docling parser
        process_start = time.time()
        print(f"🔍 [RAG] Processing document with RAG-Anything + Docling parser")
        
        # Use RAG-Anything's native document processing with Docling parser
        result = asyncio.run(rag.process_document_complete(
            file_path=temp_file_path,
            output_dir="/tmp/rag_output",
            parse_method="auto",
            parser="docling",  # Use Docling parser as specified in README
            doc_id=s3_key,
            display_stats=True
        ))
        
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
            "message": "Document processed successfully with RAG-Anything + Docling parser",
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
        return jsonify({"error": str(e)}), 500

@app.route('/query', methods=['POST'])
def process_query():
    """Process RAG query using RAG-Anything"""
    start_time = time.time()
    print(f"🔄 [RAG] Starting query processing at {time.strftime('%Y-%m-%d %H:%M:%S.%f')[:-3]}")
    
    try:
        update_activity()
        
        data = request.get_json()
        query = data.get('query', '')
        
        if not query:
            duration = time.time() - start_time
            print(f"❌ [RAG] Missing query - {duration:.3f}s")
            return jsonify({"error": "Missing query"}), 400
        
        print(f"❓ [RAG] Processing query: {query[:100]}{'...' if len(query) > 100 else ''}")
        
        # Get environment variables
        env_vars = get_environment_variables()
        
        # Initialize RAG-Anything with Docling URL
        init_start = time.time()
        rag = initialize_rag_anything(env_vars)
        init_duration = time.time() - init_start
        print(f"🚀 [RAG] RAG-Anything initialization completed in {init_duration:.3f}s")
        
        # Process query
        query_start = time.time()
        result = asyncio.run(rag.query(query))
        query_duration = time.time() - query_start
        print(f"🔍 [RAG] Query processing completed in {query_duration:.3f}s")
        
        total_duration = time.time() - start_time
        print(f"✅ [RAG] Total query time: {total_duration:.3f}s")
        
        return jsonify({
            "query": query,
            "answer": result.get('answer', 'No answer generated'),
            "sources": result.get('sources', []),
            "confidence": result.get('confidence', 0.0),
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
        return jsonify(create_error_response(str(e), total_duration, query)), 500

def main():
    """Main function for processing documents or queries"""
    # Check if we have a query to process
    query = os.environ.get('QUERY')
    s3_bucket = os.environ.get('S3_BUCKET')
    s3_key = os.environ.get('S3_KEY')
    
    if query:
        # Process RAG query
        print(f"Processing RAG query: {query}")
        try:
            env_vars = get_environment_variables()
            rag = initialize_rag_anything(env_vars)
            
            result = asyncio.run(rag.query(query))
            print(json.dumps(result, indent=2))
            
        except Exception as e:
            print(f"Error processing query: {str(e)}")
    
    elif s3_bucket and s3_key:
        # Process document
        print(f"Processing document: s3://{s3_bucket}/{s3_key}")
        try:
            # Call the Flask endpoint internally
            with app.test_client() as client:
                response = client.post('/process', json={
                    'bucket': s3_bucket,
                    'key': s3_key
                })
                print(f"Document processing result: {response.get_json()}")
                
        except Exception as e:
            print(f"Error processing document: {str(e)}")
    
    else:
        print("No query or document to process. Starting Flask server...")
        # Run Flask server
        port = int(os.environ.get('PORT', 8000))
        app.run(host='0.0.0.0', port=port, debug=True)

if __name__ == '__main__':
    main()
