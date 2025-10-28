import json
import boto3
import os

dynamodb = boto3.resource('dynamodb')
connections_table = dynamodb.Table(os.environ['CONNECTIONS_TABLE'])

def lambda_handler(event, context):
    """Handle WebSocket disconnect event"""
    connection_id = event['requestContext']['connectionId']
    
    # Remove connection from DynamoDB
    try:
        connections_table.delete_item(
            Key={'connectionId': connection_id}
        )
        print(f"WebSocket connection removed: {connection_id}")
    except Exception as e:
        print(f"Error removing connection: {str(e)}")
    
    return {
        'statusCode': 200
    }

