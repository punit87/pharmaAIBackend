import json
import boto3
import os

def lambda_handler(event, context):
    """
    Knowledge base endpoint - lists documents in S3
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
        bucket_name = os.environ.get('S3_BUCKET', '')
        
        if not bucket_name:
            return {
                'statusCode': 200,
                'headers': {
                    'Content-Type': 'application/json',
                    'Access-Control-Allow-Origin': '*'
                },
                'body': json.dumps({
                    'documents': [],
                    'message': 'No documents available'
                })
            }
        
        # List documents from S3
        s3_client = boto3.client('s3')
        
        try:
            # List all objects in the test-documents prefix
            response = s3_client.list_objects_v2(
                Bucket=bucket_name,
                Prefix='test-documents/'
            )
            
            documents = []
            if 'Contents' in response:
                for obj in response['Contents']:
                    key = obj['Key']
                    filename = key.split('/')[-1]
                    
                    # Extract original filename (format: uuid_originalname.pdf)
                    original_filename = None
                    if '_' in filename:
                        parts = filename.split('_', 1)
                        if len(parts) == 2:
                            original_filename = parts[1]  # Get part after first underscore
                        else:
                            original_filename = filename
                    else:
                        # If no underscore, use the UUID filename
                        original_filename = filename
                    
                    documents.append({
                        'key': key,
                        'filename': filename,
                        'original_name': original_filename,
                        'size': obj['Size'],
                        'last_modified': obj['LastModified'].isoformat(),
                        'etag': obj['ETag'].strip('"')
                    })
            
            return {
                'statusCode': 200,
                'headers': {
                    'Content-Type': 'application/json',
                    'Access-Control-Allow-Origin': '*'
                },
                'body': json.dumps({
                    'documents': documents,
                    'count': len(documents)
                })
            }
            
        except Exception as e:
            return {
                'statusCode': 200,
                'headers': {
                    'Content-Type': 'application/json',
                    'Access-Control-Allow-Origin': '*'
                },
                'body': json.dumps({
                    'documents': [],
                    'error': str(e)
                })
            }
            
    except Exception as e:
        return {
            'statusCode': 500,
            'headers': {
                'Content-Type': 'application/json',
                'Access-Control-Allow-Origin': '*'
            },
            'body': json.dumps({'error': str(e)})
        }

