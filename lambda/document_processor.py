import json
import boto3
import os
import requests
import time
from datetime import datetime

# WebSocket utility for sending progress updates
try:
    import sys
    sys.path.append('/var/task')
    from websocket_send import send_progress_update, send_completion_notification
except ImportError:
    # Fallback if websocket_send is not available
    def send_progress_update(connection_id, step, message, data=None, api_endpoint=None):
        print(f"[WebSocket] {step}: {message} (connection_id: {connection_id})")
    
    def send_completion_notification(connection_id, success, document_key=None, error=None, api_endpoint=None):
        print(f"[WebSocket] Complete: {success} (connection_id: {connection_id})")

def lambda_handler(event, context):
    try:
        connection_id = None
        # Construct WebSocket endpoint dynamically if not set in environment
        websocket_endpoint = os.environ.get('WEBSOCKET_API_ENDPOINT')
        if not websocket_endpoint:
            # Construct from known WebSocket API ID: 6dkgg5u5s7
            region = os.environ.get('AWS_REGION', 'us-east-1')
            stage = os.environ.get('ENVIRONMENT', 'dev')
            websocket_api_id = '6dkgg5u5s7'  # Known WebSocket API Gateway ID
            websocket_endpoint = f'https://{websocket_api_id}.execute-api.{region}.amazonaws.com/{stage}'
            print(f"Constructed WebSocket endpoint: {websocket_endpoint}")
        
        # Handle S3 event (from S3 notification)
        if 'Records' in event:
            # Extract S3 event information
            record = event['Records'][0]
            bucket_name = record['s3']['bucket']['name']
            document_key = record['s3']['object']['key']
            document_name = document_key.split('/')[-1]  # Get filename from key
            
            print(f"Processing S3 event: bucket={bucket_name}, key={document_key}")
        else:
            # Handle API Gateway event (for manual testing or WebSocket tracking)
            if 'body' in event:
                body = json.loads(event['body'])
                document_key = body.get('document_key', '')
                document_name = body.get('document_name', '')
                bucket_name = body.get('bucket', os.environ.get('S3_BUCKET', ''))
                connection_id = body.get('connection_id')  # WebSocket connection ID
            else:
                document_key = event.get('document_key', '')
                document_name = event.get('document_name', '')
                bucket_name = event.get('bucket', os.environ.get('S3_BUCKET', ''))
                connection_id = event.get('connection_id')

        if not document_key:
            return {
                'statusCode': 400,
                'headers': {
                    'Content-Type': 'application/json',
                    'Access-Control-Allow-Origin': '*'
                },
                'body': json.dumps({'error': 'No document_key provided'})
            }
            
        if not bucket_name:
            return {
                'statusCode': 400,
                'headers': {
                    'Content-Type': 'application/json',
                    'Access-Control-Allow-Origin': '*'
                },
                'body': json.dumps({'error': 'No bucket name provided'})
            }

        print(f"Processing document: {document_key}")
        if document_name:
            print(f"Document name: {document_name}")

        # For API Gateway calls (without S3 Records), return immediately and process asynchronously
        # The API Gateway has a 30-second timeout, but WebSocket API has no such limit
        # So we return quickly from the REST API, then process in background and send WebSocket updates
        api_gateway_mode = 'Records' not in event
        
        if api_gateway_mode and not event.get('_async_processing'):
            print(f"API Gateway triggered processing for: {document_key}")
            
            # Send initial WebSocket update
            if connection_id:
                try:
                    send_progress_update(
                        connection_id, 
                        'starting',
                        'Starting document processing...',
                        {'document_name': document_name, 'progress': 5},
                        websocket_endpoint
                    )
                except Exception as e:
                    print(f"Error sending WebSocket update: {str(e)}")
            
            # Trigger async processing by invoking Lambda with special flag
            try:
                import boto3
                lambda_client = boto3.client('lambda')
                lambda_function_name = os.environ.get('AWS_LAMBDA_FUNCTION_NAME')
                
                # Invoke this Lambda asynchronously to do the actual processing
                lambda_client.invoke(
                    FunctionName=lambda_function_name,
                    InvocationType='Event',  # Async invocation
                    Payload=json.dumps({
                        'bucket': bucket_name,
                        'document_key': document_key,
                        'document_name': document_name,
                        'connection_id': connection_id,
                        '_async_processing': True  # Flag for async processing
                    })
                )
                print(f"Triggered async processing for: {document_key}")
            except Exception as e:
                print(f"Failed to invoke Lambda asynchronously: {str(e)}")
            
            # Return immediately to avoid API Gateway timeout
            return {
                'statusCode': 200,
                'headers': {
                    'Content-Type': 'application/json',
                    'Access-Control-Allow-Origin': '*'
                },
                'body': json.dumps({
                    'status': 'accepted',
                    'message': 'Document processing started.',
                    'document_key': document_key,
                    'document_name': document_name
                })
            }
        
        # If this is the async processing invocation, skip the early return and continue to process

        # Send initial progress update via WebSocket if connection_id is provided
        if connection_id and event.get('async_trigger'):
            send_progress_update(
                connection_id, 
                'starting',
                'Starting document processing...',
                {'document_name': document_name, 'progress': 15},
                websocket_endpoint
            )
        
        # Use ALB endpoint for reliable connection to ECS tasks (for S3 events)
        alb_endpoint = os.environ.get('ALB_ENDPOINT')
        if not alb_endpoint:
            print("ALB_ENDPOINT not configured")
            if connection_id:
                send_completion_notification(connection_id, False, document_key, 'ALB endpoint not configured', websocket_endpoint)
            return {
                'statusCode': 500,
                'headers': {
                    'Content-Type': 'application/json',
                    'Access-Control-Allow-Origin': '*'
                },
                'body': json.dumps({'error': 'ALB endpoint not configured'})
            }
        
        server_url = f"http://{alb_endpoint}"
        process_url = f"{server_url}/process"
        
        print(f"Making document processing request via ALB: {process_url}")
        
        if connection_id and api_gateway_mode:
            try:
                send_progress_update(
                    connection_id,
                    'triggering',
                    'Triggering document processing on ECS...',
                    {'progress': 20},
                    websocket_endpoint
                )
            except Exception as e:
                print(f"Error sending WebSocket update: {str(e)}")

        # Retry logic with exponential backoff
        max_retries = 5
        retry_delay = 10  # Start with 10 seconds
        process_response = None
        
        for attempt in range(max_retries):
            try:
                print(f"Attempt {attempt + 1}/{max_retries}: Making document processing request to ALB: {process_url}")
                
                # Send progress update
                if connection_id and api_gateway_mode:
                    try:
                        send_progress_update(
                            connection_id,
                            'processing',
                            f'Connecting to ECS processing task... (attempt {attempt + 1}/{max_retries})',
                            {'progress': 30 + (attempt * 10)},
                            websocket_endpoint
                        )
                    except Exception as e:
                        print(f"Error sending WebSocket update: {str(e)}")
                
                # Prepare request payload - RAG-Anything expects 'bucket' and 'key'
                payload = {
                    'bucket': bucket_name,
                    'key': document_key
                }
                if document_name:
                    payload['document_name'] = document_name
                
                # Send progress update before making request
                if connection_id and api_gateway_mode:
                    try:
                        send_progress_update(
                            connection_id,
                            'processing',
                            'Sending document to processing engine...',
                            {'progress': 40},
                            websocket_endpoint
                        )
                    except Exception as e:
                        print(f"Error sending WebSocket update: {str(e)}")
                
                process_response = requests.post(
                    process_url,
                    json=payload,
                    headers={'Content-Type': 'application/json'},
                    timeout=300  # 5 minutes timeout
                )
                
                if process_response.status_code == 200:
                    if connection_id and api_gateway_mode:
                        try:
                            send_progress_update(
                                connection_id,
                                'processing',
                                'Document processing completed successfully!',
                                {'progress': 90},
                                websocket_endpoint
                            )
                        except Exception as e:
                            print(f"Error sending WebSocket update: {str(e)}")
                    break  # Success, exit retry loop
                elif process_response.status_code == 502 or process_response.status_code == 503:
                    # ALB/task not ready, retry
                    if connection_id and api_gateway_mode:
                        send_progress_update(
                            connection_id,
                            'waiting',
                            f'Processing service not ready, retrying in {retry_delay}s...',
                            {'progress': 50},
                            websocket_endpoint
                        )
                    if attempt < max_retries - 1:
                        print(f"ALB returned {process_response.status_code}, retrying in {retry_delay} seconds...")
                        time.sleep(retry_delay)
                        retry_delay *= 2  # Exponential backoff
                        continue
                else:
                    # Other error, don't retry
                    break
                    
            except requests.exceptions.Timeout:
                print(f"Request timeout on attempt {attempt + 1}")
                if connection_id and api_gateway_mode:
                    send_progress_update(
                        connection_id,
                        'waiting',
                        'Request timeout, retrying...',
                        {'progress': 50},
                        websocket_endpoint
                    )
                if attempt < max_retries - 1:
                    time.sleep(retry_delay)
                    retry_delay *= 2
                    continue
            except requests.exceptions.ConnectionError:
                print(f"Connection error on attempt {attempt + 1}")
                if connection_id and api_gateway_mode:
                    send_progress_update(
                        connection_id,
                        'waiting',
                        'Connection error, retrying...',
                        {'progress': 50},
                        websocket_endpoint
                    )
                if attempt < max_retries - 1:
                    time.sleep(retry_delay)
                    retry_delay *= 2
                    continue
            except Exception as e:
                print(f"Unexpected error on attempt {attempt + 1}: {str(e)}")
                if connection_id and api_gateway_mode:
                    send_progress_update(
                        connection_id,
                        'error',
                        f'Error: {str(e)[:50]}...',
                        {'progress': 50},
                        websocket_endpoint
                    )
                if attempt < max_retries - 1:
                    time.sleep(retry_delay)
                    retry_delay *= 2
                    continue
        
        if process_response and process_response.status_code == 200:
            result = process_response.json()
            print("Document processed successfully")
            
            # Send completion notification via WebSocket
            if connection_id:
                send_completion_notification(
                    connection_id,
                    True,
                    document_key,
                    None,
                    websocket_endpoint
                )
            
            # Task stays running for better performance (DesiredCount=1)
            print("ECS task remains running for better performance")
            
            # Return appropriate response based on event type
            if api_gateway_mode:
                # API Gateway event - return HTTP response
                try:
                    send_completion_notification(
                        connection_id,
                        True,
                        document_key,
                        None,
                        websocket_endpoint
                    )
                except Exception as e:
                    print(f"Error sending completion notification: {str(e)}")
                    
                return {
                    'statusCode': 200,
                    'headers': {
                        'Content-Type': 'application/json',
                        'Access-Control-Allow-Origin': '*'
                    },
                    'body': json.dumps({
                        'status': 'success',
                        'message': 'Document processed successfully.',
                        'document_key': document_key,
                        'document_name': document_name,
                        'result': result
                    })
                }
            else:
                # S3 event
                if 'Records' in event:
                    # S3 event - just log success
                    print(f"Document processing completed successfully: {document_key}")
                    return {'status': 'success', 'document_key': document_key}
        else:
            if process_response:
                error_message = f'Document processing failed with status: {process_response.status_code}'
            else:
                error_message = 'Document processing failed - no response received'
            
            print(error_message)
            
            # Send error notification via WebSocket
            if connection_id:
                try:
                    send_completion_notification(
                        connection_id,
                        False,
                        document_key,
                        error_message,
                        websocket_endpoint
                    )
                except Exception as e:
                    print(f"Error sending error notification: {str(e)}")
            
            if api_gateway_mode:
                # API Gateway event - return HTTP error response
                return {
                    'statusCode': 500,
                    'headers': {
                        'Content-Type': 'application/json',
                        'Access-Control-Allow-Origin': '*'
                    },
                    'body': json.dumps({
                        'error': error_message
                    })
                }
            else:
                # S3 event - just log error
                print(f"Document processing failed: {process_response.text}")
                return {'status': 'error', 'document_key': document_key, 'error': process_response.text}
                
    except Exception as e:
        print(f"Error processing document: {str(e)}")
        import traceback
        traceback.print_exc()
        
        if api_gateway_mode:
            # API Gateway event - return HTTP error response
            return {
                'statusCode': 500,
                'headers': {
                    'Content-Type': 'application/json',
                    'Access-Control-Allow-Origin': '*'
                },
                'body': json.dumps({'error': str(e)})
            }
        else:
            # S3 event - just log error
            return {'status': 'error', 'error': str(e)}