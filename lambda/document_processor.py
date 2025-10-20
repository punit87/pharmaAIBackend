import json
import boto3
import os

def lambda_handler(event, context):
    """
    Process S3 upload events and trigger ECS tasks for document processing
    """
    try:
        ecs_client = boto3.client('ecs')
        
        for record in event['Records']:
            bucket = record['s3']['bucket']['name']
            key = record['s3']['object']['key']
            
            # Only process files in uploads/ directory
            if not key.startswith('uploads/'):
                print(f"Skipping file {key} - not in uploads directory")
                continue
            
            print(f"Processing uploaded file: {key}")
            
            # Trigger ECS task for document processing
            response = ecs_client.run_task(
                cluster=os.environ['ECS_CLUSTER'],
                taskDefinition=os.environ['DOCLING_TASK_DEFINITION'],
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
                            'name': 'docling',
                            'environment': [
                                {'name': 'S3_BUCKET', 'value': bucket},
                                {'name': 'S3_KEY', 'value': key},
                                {'name': 'AWS_DEFAULT_REGION', 'value': os.environ['AWS_DEFAULT_REGION']},
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
            print(f"Triggered ECS task for {key}: {task_arn}")
        
        return {'statusCode': 200}
        
    except Exception as e:
        print(f"Error processing S3 event: {str(e)}")
        return {'statusCode': 500}
