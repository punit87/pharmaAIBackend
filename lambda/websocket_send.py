"""
Utility module for sending WebSocket messages during document processing
"""
import json
import boto3
import os

def send_progress_update(connection_id, step, message, data=None, api_endpoint=None):
    """
    Send a progress update via WebSocket
    
    Args:
        connection_id: The WebSocket connection ID
        step: Current processing step
        message: Human-readable message
        data: Optional additional data
        api_endpoint: API Gateway WebSocket endpoint
    """
    if not api_endpoint:
        # Try to get from environment
        api_endpoint = os.environ.get('WEBSOCKET_API_ENDPOINT')
    
    if not api_endpoint:
        print(f"WebSocket API endpoint not configured, skipping message to {connection_id}")
        return
    
    try:
        # Construct endpoint URL
        endpoint_url = f"https://{api_endpoint}"
        apigateway = boto3.client(
            'apigatewaymanagementapi',
            endpoint_url=endpoint_url,
            region_name=os.environ.get('AWS_REGION', 'us-east-1')
        )
        
        # Send the message
        payload = {
            'type': 'progress',
            'step': step,
            'message': message,
            'timestamp': json.dumps(dict(), default=str),
            'data': data or {}
        }
        
        apigateway.post_to_connection(
            ConnectionId=connection_id,
            Data=json.dumps(payload)
        )
        
        print(f"Sent progress update to {connection_id}: {step} - {message}")
        
    except Exception as e:
        print(f"Error sending WebSocket message: {str(e)}")
        # Don't fail processing if WebSocket fails
        pass

def send_completion_notification(connection_id, success, document_key=None, error=None, api_endpoint=None):
    """
    Send completion notification via WebSocket
    
    Args:
        connection_id: The WebSocket connection ID
        success: Whether processing succeeded
        document_key: The document key
        error: Error message if failed
        api_endpoint: API Gateway WebSocket endpoint
    """
    if not api_endpoint:
        api_endpoint = os.environ.get('WEBSOCKET_API_ENDPOINT')
    
    if not api_endpoint:
        print(f"WebSocket API endpoint not configured, skipping completion notification")
        return
    
    try:
        endpoint_url = f"https://{api_endpoint}"
        apigateway = boto3.client(
            'apigatewaymanagementapi',
            endpoint_url=endpoint_url,
            region_name=os.environ.get('AWS_REGION', 'us-east-1')
        )
        
        payload = {
            'type': 'complete',
            'success': success,
            'document_key': document_key,
            'error': error,
            'timestamp': json.dumps(dict(), default=str)
        }
        
        apigateway.post_to_connection(
            ConnectionId=connection_id,
            Data=json.dumps(payload)
        )
        
        print(f"Sent completion notification to {connection_id}")
        
    except Exception as e:
        print(f"Error sending completion notification: {str(e)}")

