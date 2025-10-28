import json
import boto3
import os

apigateway = boto3.client('apigatewaymanagementapi', 
                         endpoint_url=os.environ['API_ENDPOINT'])
dynamodb = boto3.resource('dynamodb')
connections_table = dynamodb.Table(os.environ['CONNECTIONS_TABLE'])

def lambda_handler(event, context):
    """Handle WebSocket message event"""
    connection_id = event['requestContext']['connectionId']
    
    try:
        # Echo back the message (or implement custom logic)
        body = json.loads(event.get('body', '{}'))
        
        # Send response
        response = {
            'action': 'message',
            'data': body
        }
        
        apigateway.post_to_connection(
            ConnectionId=connection_id,
            Data=json.dumps(response)
        )
        
        print(f"Sent message to connection: {connection_id}")
        
        return {
            'statusCode': 200
        }
    except Exception as e:
        print(f"Error sending message: {str(e)}")
        return {
            'statusCode': 500
        }

