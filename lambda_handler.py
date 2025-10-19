import json
import os
import boto3
import tempfile
from raganything import RAGAnything, RAGAnythingConfig
from lightrag.llm.openai import openai_complete_if_cache, openai_embed
from lightrag.utils import EmbeddingFunc

# Initialize S3 client
s3_client = boto3.client('s3')

def download_from_s3(bucket, key, local_path):
    """Download file from S3 to local path"""
    try:
        s3_client.download_file(bucket, key, local_path)
        return True
    except Exception as e:
        print(f"Error downloading from S3: {str(e)}")
        return False

def process_s3_document(bucket, key, rag):
    """Process document from S3 using RAG-Anything"""
    try:
        # Create temporary file
        with tempfile.NamedTemporaryFile(delete=False, suffix='.pdf') as tmp_file:
            local_path = tmp_file.name
        
        # Download from S3
        if not download_from_s3(bucket, key, local_path):
            return False, "Failed to download document from S3"
        
        # Process with RAG-Anything
        print(f"Processing S3 document: s3://{bucket}/{key}")
        rag.insert(local_path)
        
        # Clean up
        os.unlink(local_path)
        
        print("S3 document processed successfully")
        return True, "Document processed successfully"
        
    except Exception as e:
        print(f"Error processing S3 document: {str(e)}")
        return False, str(e)

def lambda_handler(event, context):
    """
    AWS Lambda handler for RAG-Anything
    """
    try:
        # Check if this is an S3 event
        if 'Records' in event:
            # Handle S3 trigger event
            for record in event['Records']:
                if record['eventName'].startswith('ObjectCreated'):
                    bucket = record['s3']['bucket']['name']
                    key = record['s3']['object']['key']
                    
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
                    
                    rag = RAGAnything(
                        config=config,
                        llm_model_func=llm_model_func,
                        embedding_func=embedding_func,
                    )
                    
                    # Process S3 document
                    success, message = process_s3_document(bucket, key, rag)
                    
                    return {
                        'statusCode': 200 if success else 500,
                        'body': json.dumps({
                            'bucket': bucket,
                            'key': key,
                            'status': 'success' if success else 'error',
                            'message': message
                        })
                    }
        
        # Handle regular API requests
        if 'body' in event:
            body = json.loads(event['body']) if isinstance(event['body'], str) else event['body']
            query = body.get('query', '')
            document = body.get('document', '')
            s3_bucket = body.get('s3_bucket', '')
            s3_key = body.get('s3_key', '')
        else:
            query = event.get('query', '')
            document = event.get('document', '')
            s3_bucket = event.get('s3_bucket', '')
            s3_key = event.get('s3_key', '')
        
        if not query and not s3_bucket:
            return {
                'statusCode': 400,
                'body': json.dumps({'error': 'Query parameter or S3 bucket/key is required'})
            }
        
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
        
        rag = RAGAnything(
            config=config,
            llm_model_func=llm_model_func,
            embedding_func=embedding_func,
        )
        
        # Process document if provided
        if document or (s3_bucket and s3_key):
            try:
                if s3_bucket and s3_key:
                    # Process S3 document
                    success, message = process_s3_document(s3_bucket, s3_key, rag)
                    if not success:
                        return {
                            'statusCode': 500,
                            'body': json.dumps({
                                'error': 'S3 document processing failed',
                                'message': message
                            })
                        }
                elif document:
                    # Handle different document types
                    if document.startswith('http'):
                        # Download document from URL
                        import requests
                        response = requests.get(document)
                        if response.status_code == 200:
                            # Save to temporary file
                            with tempfile.NamedTemporaryFile(delete=False, suffix='.pdf') as tmp_file:
                                tmp_file.write(response.content)
                                document_path = tmp_file.name
                        else:
                            return {
                                'statusCode': 400,
                                'body': json.dumps({'error': 'Failed to download document from URL'})
                            }
                    else:
                        # Assume document is base64 encoded content
                        import base64
                        try:
                            # Decode base64 content
                            document_content = base64.b64decode(document)
                            # Save to temporary file
                            with tempfile.NamedTemporaryFile(delete=False, suffix='.pdf') as tmp_file:
                                tmp_file.write(document_content)
                                document_path = tmp_file.name
                        except Exception as e:
                            return {
                                'statusCode': 400,
                                'body': json.dumps({'error': f'Invalid document format: {str(e)}'})
                            }
                    
                    # Process document with RAG-Anything
                    print(f"Processing document: {document_path}")
                    rag.insert(document_path)
                    
                    # Clean up temporary file
                    os.unlink(document_path)
                    print("Document processed successfully")
                
            except Exception as e:
                print(f"Error processing document: {str(e)}")
                return {
                    'statusCode': 500,
                    'body': json.dumps({
                        'error': 'Document processing failed',
                        'message': str(e)
                    })
                }
        
        # Query the RAG system
        result = rag.query(query, mode="hybrid")
        
        return {
            'statusCode': 200,
            'body': json.dumps({
                'query': query,
                'answer': result,
                'requestId': context.aws_request_id
            })
        }
        
    except Exception as e:
        return {
            'statusCode': 500,
            'body': json.dumps({
                'error': 'Query processing failed',
                'message': str(e)
            })
        }
