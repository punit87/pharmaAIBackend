import json
import boto3
import os
import requests

def lambda_handler(event, context):
    """
    Delete document from S3 and remove from Neo4j knowledge base
    """
    # Handle CORS preflight
    if event.get('httpMethod') == 'OPTIONS':
        return {
            'statusCode': 200,
            'headers': {
                'Access-Control-Allow-Origin': '*',
                'Access-Control-Allow-Methods': 'OPTIONS,POST',
                'Access-Control-Allow-Headers': 'Content-Type,Authorization'
            },
            'body': ''
        }
    
    try:
        # Parse request body
        if isinstance(event.get('body'), str):
            body = json.loads(event['body'])
        else:
            body = event.get('body', {})
        
        document_key = body.get('document_key')
        
        if not document_key:
            return {
                'statusCode': 400,
                'headers': {
                    'Content-Type': 'application/json',
                    'Access-Control-Allow-Origin': '*'
                },
                'body': json.dumps({'error': 'document_key is required'})
            }
        
        bucket_name = os.environ.get('S3_BUCKET')
        alb_endpoint = os.environ.get('ALB_ENDPOINT')
        
        # Step 1: Delete from S3
        s3_client = boto3.client('s3')
        try:
            s3_client.delete_object(Bucket=bucket_name, Key=document_key)
            print(f"Deleted document from S3: {document_key}")
        except Exception as e:
            print(f"Error deleting from S3: {str(e)}")
        
        # Step 2: Delete from Neo4j knowledge base via ECS service
        if alb_endpoint:
            try:
                # Extract filename from key (format: test-documents/uuid_filename.pdf)
                filename = document_key.split('/')[-1]
                
                # Remove UUID prefix if present
                if '_' in filename:
                    original_filename = '_'.join(filename.split('_')[1:])
                else:
                    original_filename = None
                
                if original_filename:
                    print(f"Attempting to delete from Neo4j via ECS: {original_filename}")
                    
                    # Call ECS service to delete document from Neo4j
                    server_url = f"http://{alb_endpoint}"
                    delete_url = f"{server_url}/delete-document"
                    
                    delete_payload = {
                        'filename': original_filename
                    }
                    
                    try:
                        response = requests.post(
                            delete_url,
                            json=delete_payload,
                            headers={'Content-Type': 'application/json'},
                            timeout=60
                        )
                        if response.status_code == 200:
                            print(f"Successfully deleted from Neo4j: {original_filename}")
                        else:
                            print(f"Failed to delete from Neo4j: {response.status_code}")
                    except Exception as e:
                        print(f"Error calling ECS to delete from Neo4j: {str(e)}")
                    
            except Exception as e:
                print(f"Error deleting from Neo4j: {str(e)}")
        
        return {
            'statusCode': 200,
            'headers': {
                'Content-Type': 'application/json',
                'Access-Control-Allow-Origin': '*'
            },
            'body': json.dumps({
                'status': 'success',
                'message': 'Document deleted successfully',
                'document_key': document_key
            })
        }
        
    except Exception as e:
        print(f"Error in document_deleter: {str(e)}")
        return {
            'statusCode': 500,
            'headers': {
                'Content-Type': 'application/json',
                'Access-Control-Allow-Origin': '*'
            },
            'body': json.dumps({'error': str(e)})
        }

