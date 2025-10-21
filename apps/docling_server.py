#!/usr/bin/env python3
"""
Docling Server - Simple HTTP server for document processing with auto-stop
"""
import os
import json
import boto3
import threading
import time
from flask import Flask, request, jsonify
from docling.document_converter import DocumentConverter
import tempfile

app = Flask(__name__)

# Initialize document converter
converter = DocumentConverter()

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
    return jsonify({"status": "healthy", "service": "docling"})

@app.route('/parse', methods=['POST'])
def parse_document():
    """Parse document using Docling"""
    try:
        update_activity()
        
        if 'file' not in request.files:
            return jsonify({"error": "No file provided"}), 400
        
        file = request.files['file']
        if file.filename == '':
            return jsonify({"error": "No file selected"}), 400
        
        # Save uploaded file temporarily
        temp_file_path = f"/tmp/{file.filename}"
        file.save(temp_file_path)
        
        try:
            # Process document with Docling
            result = converter.convert(temp_file_path)
            
            # Extract text content
            content = ""
            if hasattr(result, 'document') and hasattr(result.document, 'text'):
                content = result.document.text
            elif hasattr(result, 'text'):
                content = result.text
            else:
                # Try to extract text from any available source
                content = str(result)
            
            # Clean up temp file
            os.remove(temp_file_path)
            
            return jsonify({
                "status": "success",
                "filename": file.filename,
                "content": content,
                "content_length": len(content),
                "message": "Document parsed successfully"
            })
            
        except Exception as e:
            # Clean up temp file on error
            if os.path.exists(temp_file_path):
                os.remove(temp_file_path)
            raise e
        
    except Exception as e:
        print(f"Error parsing document: {str(e)}")
        return jsonify({"error": str(e)}), 500

@app.route('/process', methods=['POST'])
def process_document():
    """Process document from S3"""
    try:
        data = request.get_json()
        s3_bucket = data.get('bucket')
        s3_key = data.get('key')
        
        if not s3_bucket or not s3_key:
            return jsonify({"error": "Missing bucket or key"}), 400
        
        # Download file from S3
        s3_client = boto3.client('s3')
        with tempfile.NamedTemporaryFile(suffix='.pdf', delete=False) as temp_file:
            s3_client.download_file(s3_bucket, s3_key, temp_file.name)
            
            # Process document with Docling
            doc = converter.convert(temp_file.name)
            
            # Extract text content
            text_content = doc.export_to_markdown()
            
            # Store processed content back to S3
            processed_key = s3_key.replace('uploads/', 'processed/').replace('.pdf', '.md')
            s3_client.put_object(
                Bucket=s3_bucket,
                Key=processed_key,
                Body=text_content.encode('utf-8'),
                ContentType='text/markdown'
            )
            
            # Clean up temp file
            os.unlink(temp_file.name)
            
            return jsonify({
                "status": "success",
                "processed_key": processed_key,
                "text_length": len(text_content)
            })
            
    except Exception as e:
        return jsonify({"error": str(e)}), 500

@app.route('/convert', methods=['POST'])
def convert_document():
    """Convert document and return text content"""
    try:
        data = request.get_json()
        s3_bucket = data.get('bucket')
        s3_key = data.get('key')
        
        if not s3_bucket or not s3_key:
            return jsonify({"error": "Missing bucket or key"}), 400
        
        # Download file from S3
        s3_client = boto3.client('s3')
        with tempfile.NamedTemporaryFile(suffix='.pdf', delete=False) as temp_file:
            s3_client.download_file(s3_bucket, s3_key, temp_file.name)
            
            # Process document with Docling
            doc = converter.convert(temp_file.name)
            
            # Extract text content
            text_content = doc.export_to_markdown()
            
            # Clean up temp file
            os.unlink(temp_file.name)
            
            return jsonify({
                "status": "success",
                "text_content": text_content,
                "text_length": len(text_content)
            })
            
    except Exception as e:
        return jsonify({"error": str(e)}), 500

if __name__ == '__main__':
    port = int(os.environ.get('PORT', 8000))
    app.run(host='0.0.0.0', port=port, debug=True)
