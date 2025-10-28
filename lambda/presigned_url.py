import json
import boto3
import os

def lambda_handler(event, context):
    try:
        # Get S3 bucket name from environment variable
        bucket_name = os.environ['S3_BUCKET']
        
        print(f"Event received: {json.dumps(event)}")
        
        # Get original filename from query params or request body
        original_filename = None
        if event.get('queryStringParameters'):
            print(f"Query params: {event['queryStringParameters']}")
            original_filename = event['queryStringParameters'].get('filename')
            print(f"Original filename from query: {original_filename}")
        elif event.get('body'):
            try:
                body = json.loads(event['body'])
                original_filename = body.get('filename')
                print(f"Original filename from body: {original_filename}")
            except:
                pass
        
        # Generate presigned URL for PUT request
        s3_client = boto3.client('s3')
        
        # Generate a unique key for the file, preserving original filename if provided
        import uuid
        if original_filename:
            # Preserve original filename with UUID prefix to ensure uniqueness
            safe_filename = original_filename.replace(' ', '_').replace('/', '_').replace('\\', '_')
            file_key = f"test-documents/{uuid.uuid4()}_{safe_filename}"
        else:
            file_key = f"test-documents/{uuid.uuid4()}.pdf"
        
        # Generate presigned URL for PUT request
        # IMPORTANT: ContentType must be included in the signature for the client to send it
        presigned_url = s3_client.generate_presigned_url(
            'put_object',
            Params={
                'Bucket': bucket_name,
                'Key': file_key,
                'ContentType': 'application/pdf'
            },
            ExpiresIn=300  # 5 minutes
        )
        
        return {
            'statusCode': 200,
            'headers': {
                'Content-Type': 'application/json',
                'Access-Control-Allow-Origin': '*'
            },
            'body': json.dumps({
                'presigned_url': presigned_url,
                'bucket': bucket_name,
                'key': file_key,
                'upload_method': 'PUT',
                'expires_in': 300
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
