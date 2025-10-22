import json
import boto3
import os

def lambda_handler(event, context):
    try:
        ecs_client = boto3.client('ecs')
        
        response = ecs_client.list_tasks(
            cluster=os.environ['ECS_CLUSTER'],
            desiredStatus='RUNNING'
        )
        
        task_count = len(response['taskArns'])
        
        return {
            'statusCode': 200,
            'headers': {
                'Content-Type': 'application/json',
                'Access-Control-Allow-Origin': '*'
            },
            'body': json.dumps({
                'status': 'healthy',
                'service': 'pharma-rag',
                'ecs_tasks': {
                    'total': task_count,
                    'running': task_count,
                    'task_arns': response['taskArns']
                },
                'timestamp': context.aws_request_id
            })
        }
    except Exception as e:
        return {
            'statusCode': 500,
            'headers': {
                'Content-Type': 'application/json',
                'Access-Control-Allow-Origin': '*'
            },
            'body': json.dumps({
                'status': 'unhealthy',
                'error': str(e)
            })
        }
