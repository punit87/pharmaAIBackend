import json
import boto3
import os
from datetime import datetime, timedelta

s3_client = boto3.client('s3')

def lambda_handler(event, context):
    """
    Generate presigned URL for document upload
    GET /presigned-url
    """
    try:
        bucket_name = os.environ['S3_BUCKET']
        
        # Generate unique file name with timestamp
        timestamp = datetime.now().strftime('%Y/%m/%d/%H%M%S')
        file_name = f"uploads/{timestamp}/{context.aws_request_id}.pdf"
        
        # Generate presigned URL valid for 30 seconds
        presigned_url = s3_client.generate_presigned_url(
            'put_object',
            Params={
                'Bucket': bucket_name, 
                'Key': file_name,
                'ContentType': 'application/pdf'
            },
            ExpiresIn=30
        )
        
        return {
            'statusCode': 200,
            'headers': {
                'Content-Type': 'application/json',
                'Access-Control-Allow-Origin': '*',
                'Access-Control-Allow-Methods': 'GET, POST, OPTIONS',
                'Access-Control-Allow-Headers': 'Content-Type'
            },
            'body': json.dumps({
                'presigned_url': presigned_url,
                'file_name': file_name,
                'expires_in': 30,
                'bucket': bucket_name
            })
        }
    except Exception as e:
        print(f"Error generating presigned URL: {str(e)}")
        return {
            'statusCode': 500,
            'headers': {'Content-Type': 'application/json'},
            'body': json.dumps({'error': str(e)})
        }
