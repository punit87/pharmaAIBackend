import json
import boto3
import os

def lambda_handler(event, context):
    try:
        # Get S3 bucket name from environment variable
        bucket_name = os.environ['S3_BUCKET']
        
        # Generate presigned URL for PUT request
        s3_client = boto3.client('s3')
        
        # Generate a unique key for the file
        import uuid
        file_key = f"test-documents/{uuid.uuid4()}.pdf"
        
        presigned_url = s3_client.generate_presigned_url(
            'put_object',
            Params={
                'Bucket': bucket_name,
                'Key': file_key
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
