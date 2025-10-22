import json
import boto3
import os

def lambda_handler(event, context):
    try:
        ecs_client = boto3.client('ecs')
        
        # Get the service name from environment variables
        service_name = os.environ['ECS_SERVICE_NAME']
        cluster_name = os.environ['ECS_CLUSTER']
        
        # Scale up the service to 1 task
        response = ecs_client.update_service(
            cluster=cluster_name,
            service=service_name,
            desiredCount=1
        )
        
        print(f"Scaled up ECS service {service_name} to 1 task")
        
        return {
            'statusCode': 200,
            'headers': {
                'Content-Type': 'application/json',
                'Access-Control-Allow-Origin': '*'
            },
            'body': json.dumps({
                'status': 'success',
                'message': f'Scaled up ECS service {service_name}',
                'service_name': service_name,
                'desired_count': 1
            })
        }
        
    except Exception as e:
        print(f"Error scaling ECS service: {str(e)}")
        return {
            'statusCode': 500,
            'headers': {
                'Content-Type': 'application/json',
                'Access-Control-Allow-Origin': '*'
            },
            'body': json.dumps({
                'error': str(e)
            })
        }
