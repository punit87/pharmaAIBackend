import json
import boto3
import os
import requests

apigateway = boto3.client('apigatewaymanagementapi', 
                         endpoint_url=os.environ['API_ENDPOINT'])
dynamodb = boto3.resource('dynamodb')
connections_table = dynamodb.Table(os.environ['CONNECTIONS_TABLE'])

def lambda_handler(event, context):
    """Handle WebSocket message event - process document processing requests"""
    connection_id = event['requestContext']['connectionId']
    
    try:
        body = json.loads(event.get('body', '{}'))
        action = body.get('action')
        
        print(f"WebSocket message received - action={action}, connection_id={connection_id}")
        
        if action == 'process_document':
            # Handle document processing request
            bucket = body.get('bucket')
            document_key = body.get('document_key')
            document_name = body.get('document_name')
            
            if not document_key:
                _send_error(connection_id, 'Missing document_key')
                return {'statusCode': 400}
            
            # Get environment variables
            alb_endpoint = os.environ.get('ALB_ENDPOINT')
            s3_bucket = os.environ.get('S3_BUCKET')
            
            if not alb_endpoint:
                _send_error(connection_id, 'ALB endpoint not configured')
                return {'statusCode': 500}
            
            # Send progress updates
            _send_update(connection_id, 'starting', 'Starting document processing...', 10)
            _send_update(connection_id, 'triggering', 'Connecting to ECS processing service...', 20)
            
            # Trigger ECS processing
            server_url = f"http://{alb_endpoint}"
            process_url = f"{server_url}/process"
            
            payload = {
                'bucket': bucket or s3_bucket,
                'key': document_key
            }
            if document_name:
                payload['document_name'] = document_name
            
            _send_update(connection_id, 'processing', 'Sending document to processing engine...', 40)
            
            # Call ECS to process document
            print(f"Making HTTP request to ECS: {process_url}")
            print(f"Payload: {json.dumps(payload)}")
            try:
                process_response = requests.post(
                    process_url,
                    json=payload,
                    headers={'Content-Type': 'application/json'},
                    timeout=300
                )
                print(f"HTTP response status: {process_response.status_code}")
                print(f"HTTP response body: {process_response.text}")
            except Exception as e:
                print(f"Error making HTTP request to ECS: {str(e)}")
                import traceback
                traceback.print_exc()
                _send_error(connection_id, f'Error calling ECS: {str(e)}')
                return {'statusCode': 500}
            
            if process_response.status_code == 200:
                _send_update(connection_id, 'complete', 'Document processing completed successfully!', 100)
                return {'statusCode': 200}
            else:
                error_msg = f'Processing failed: {process_response.status_code}'
                _send_error(connection_id, error_msg)
                return {'statusCode': 500}
        
        # Handle other actions
        response = {'action': 'message', 'data': body}
        apigateway.post_to_connection(
            ConnectionId=connection_id,
            Data=json.dumps(response)
        )
        
        return {'statusCode': 200}
        
    except Exception as e:
        print(f"Error handling WebSocket message: {str(e)}")
        import traceback
        traceback.print_exc()
        _send_error(connection_id, str(e))
        return {'statusCode': 500}

def _send_update(connection_id, step, message, progress):
    """Send progress update via WebSocket"""
    try:
        payload = {
            'action': 'progressUpdate',
            'step': step,
            'message': message,
            'data': {'progress': progress}
        }
        apigateway.post_to_connection(
            ConnectionId=connection_id,
            Data=json.dumps(payload)
        )
        print(f"Sent progress update: {step} - {message} ({progress}%)")
    except Exception as e:
        print(f"Error sending progress update: {str(e)}")

def _send_error(connection_id, error_msg):
    """Send error message via WebSocket"""
    try:
        payload = {
            'action': 'error',
            'message': error_msg
        }
        apigateway.post_to_connection(
            ConnectionId=connection_id,
            Data=json.dumps(payload)
        )
    except Exception as e:
        print(f"Error sending error message: {str(e)}")

