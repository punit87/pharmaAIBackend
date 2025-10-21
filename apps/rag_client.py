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
from typing import Dict, Any
from flask import Flask, request, jsonify

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
    try:
        update_activity()
        
        data = request.get_json()
        s3_bucket = data.get('bucket')
        s3_key = data.get('key')
        
        if not s3_bucket or not s3_key:
            return jsonify({"error": "Missing bucket or key"}), 400
        
        # Get environment variables
        neo4j_uri = os.environ.get('NEO4J_URI')
        neo4j_username = os.environ.get('NEO4J_USERNAME')
        neo4j_password = os.environ.get('NEO4J_PASSWORD')
        openai_api_key = os.environ.get('OPENAI_API_KEY')
        docling_url = os.environ.get('DOCLING_SERVICE_URL', 'http://localhost:8000')
        
        # Download file from S3
        s3_client = boto3.client('s3')
        temp_file_path = f"/tmp/{os.path.basename(s3_key)}"
        s3_client.download_file(s3_bucket, s3_key, temp_file_path)
        
        # Call Docling service for document parsing
        print(f"Calling Docling service at {docling_url} for document parsing")
        
        with open(temp_file_path, 'rb') as file:
            files = {'file': (os.path.basename(s3_key), file, 'application/octet-stream')}
            response = requests.post(f"{docling_url}/parse", files=files, timeout=300)
            response.raise_for_status()
            
            docling_result = response.json()
            print(f"Docling parsing result: {docling_result}")
        
        # Now use RAG-Anything for RAG processing with the parsed content
        from raganything import RAGAnything
        
        # Initialize RAG-Anything
        rag = RAGAnything(
            neo4j_uri=neo4j_uri,
            neo4j_username=neo4j_username,
            neo4j_password=neo4j_password,
            openai_api_key=openai_api_key
        )
        
        # Process the parsed content with RAG-Anything
        # We'll use the parsed content from Docling
        parsed_content = docling_result.get('content', '')
        
        if parsed_content:
            # Store the parsed content in Neo4j using RAG-Anything
            result = asyncio.run(rag.process_content(
                content=parsed_content,
                doc_id=s3_key,
                content_type="document"
            ))
        else:
            result = {"error": "No content parsed from Docling"}
        
        # Clean up temp file
        os.remove(temp_file_path)
        
        return jsonify({
            "status": "success",
            "result": result,
            "docling_result": docling_result,
            "message": "Document processed successfully with Docling + RAG-Anything"
        })
        
    except Exception as e:
        print(f"Error processing document: {str(e)}")
        return jsonify({"error": str(e)}), 500

@app.route('/query', methods=['POST'])
def process_query():
    """Process RAG query using RAG-Anything"""
    try:
        update_activity()
        
        data = request.get_json()
        query = data.get('query', '')
        
        if not query:
            return jsonify({"error": "Missing query"}), 400
        
        # Get environment variables
        neo4j_uri = os.environ.get('NEO4J_URI')
        neo4j_username = os.environ.get('NEO4J_USERNAME')
        neo4j_password = os.environ.get('NEO4J_PASSWORD')
        openai_api_key = os.environ.get('OPENAI_API_KEY')
        
        # Import RAG-Anything
        from raganything import RAGAnything
        
        # Initialize RAG-Anything
        rag = RAGAnything(
            neo4j_uri=neo4j_uri,
            neo4j_username=neo4j_username,
            neo4j_password=neo4j_password,
            openai_api_key=openai_api_key
        )
        
        # Process query
        result = asyncio.run(rag.query(query))
        
        return jsonify({
            "query": query,
            "answer": result.get('answer', 'No answer generated'),
            "sources": result.get('sources', []),
            "confidence": result.get('confidence', 0.0),
            "status": "completed"
        })
        
    except Exception as e:
        print(f"Error processing query: {str(e)}")
        return jsonify({
            "query": query,
            "answer": f"Error processing query: {str(e)}",
            "sources": [],
            "confidence": 0.0,
            "status": "error"
        }), 500

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
            from raganything import RAGAnything
            
            neo4j_uri = os.environ.get('NEO4J_URI')
            neo4j_username = os.environ.get('NEO4J_USERNAME')
            neo4j_password = os.environ.get('NEO4J_PASSWORD')
            openai_api_key = os.environ.get('OPENAI_API_KEY')
            
            rag = RAGAnything(
                neo4j_uri=neo4j_uri,
                neo4j_username=neo4j_username,
                neo4j_password=neo4j_password,
                openai_api_key=openai_api_key
            )
            
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
