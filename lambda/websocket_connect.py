import json
import boto3
import os
from datetime import datetime, timedelta

dynamodb = boto3.resource('dynamodb')
connections_table = dynamodb.Table(os.environ['CONNECTIONS_TABLE'])

def lambda_handler(event, context):
    """Handle WebSocket connect event"""
    connection_id = event['requestContext']['connectionId']
    
    # Store connection in DynamoDB with 1 hour TTL
    connections_table.put_item(
        Item={
            'connectionId': connection_id,
            'connectedAt': datetime.utcnow().isoformat(),
            'ttl': int((datetime.utcnow() + timedelta(hours=1)).timestamp())
        }
    )
    
    print(f"WebSocket connection established: {connection_id}")
    
    return {
        'statusCode': 200
    }

