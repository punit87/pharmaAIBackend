import json
import boto3
import os
import requests
import time

def lambda_handler(event, context):
    """
    Handle RAG query requests
    POST /rag-query
    Body: {"query": "your question here"}
    """
    try:
        # Parse request body
        if isinstance(event['body'], str):
            body = json.loads(event['body'])
        else:
            body = event['body']
            
        query = body.get('query', '')
        if not query:
            return {
                'statusCode': 400,
                'headers': {'Content-Type': 'application/json'},
                'body': json.dumps({'error': 'Query parameter is required'})
            }
        
        # Trigger ECS task for RAG processing
        ecs_client = boto3.client('ecs')
        
        response = ecs_client.run_task(
            cluster=os.environ['ECS_CLUSTER'],
            taskDefinition=os.environ['RAGANYTHING_TASK_DEFINITION'],
            launchType='FARGATE',
            networkConfiguration={
                'awsvpcConfiguration': {
                    'subnets': os.environ['SUBNETS'].split(','),
                    'securityGroups': [os.environ['SECURITY_GROUP']],
                    'assignPublicIp': 'ENABLED'
                }
            },
            overrides={
                'containerOverrides': [
                    {
                        'name': 'raganything',
                        'environment': [
                            {'name': 'QUERY', 'value': query},
                            {'name': 'AWS_DEFAULT_REGION', 'value': os.environ['AWS_DEFAULT_REGION']},
                            {'name': 'S3_BUCKET', 'value': os.environ['S3_BUCKET']},
                            {'name': 'NEO4J_URI', 'value': os.environ['NEO4J_URI']},
                            {'name': 'NEO4J_USERNAME', 'value': os.environ['NEO4J_USERNAME']},
                            {'name': 'NEO4J_PASSWORD', 'value': os.environ['NEO4J_PASSWORD']},
                            {'name': 'OPENAI_API_KEY', 'value': os.environ['OPENAI_API_KEY']}
                        ]
                    }
                ]
            }
        )
        
        task_arn = response['tasks'][0]['taskArn']
        
        # Wait for task completion (with timeout)
        max_wait_time = 300  # 5 minutes
        start_time = time.time()
        
        while time.time() - start_time < max_wait_time:
            task_response = ecs_client.describe_tasks(
                cluster=os.environ['ECS_CLUSTER'],
                tasks=[task_arn]
            )
            
            task = task_response['tasks'][0]
            last_status = task['lastStatus']
            
            if last_status == 'STOPPED':
                # Check exit code
                exit_code = task['containers'][0].get('exitCode', 1)
                if exit_code == 0:
                    # Task completed successfully
                    # In a real implementation, you'd retrieve results from S3 or database
                    return {
                        'statusCode': 200,
                        'headers': {
                            'Content-Type': 'application/json',
                            'Access-Control-Allow-Origin': '*'
                        },
                        'body': json.dumps({
                            'query': query,
                            'task_arn': task_arn,
                            'status': 'completed',
                            'message': 'RAG query processed successfully'
                        })
                    }
                else:
                    return {
                        'statusCode': 500,
                        'headers': {'Content-Type': 'application/json'},
                        'body': json.dumps({
                            'error': 'RAG processing failed',
                            'task_arn': task_arn,
                            'exit_code': exit_code
                        })
                    }
            
            time.sleep(5)  # Wait 5 seconds before checking again
        
        # Timeout reached
        return {
            'statusCode': 408,
            'headers': {'Content-Type': 'application/json'},
            'body': json.dumps({
                'error': 'Request timeout',
                'task_arn': task_arn,
                'message': 'RAG processing is taking longer than expected'
            })
        }
        
    except Exception as e:
        print(f"Error processing RAG query: {str(e)}")
        return {
            'statusCode': 500,
            'headers': {'Content-Type': 'application/json'},
            'body': json.dumps({'error': str(e)})
        }
