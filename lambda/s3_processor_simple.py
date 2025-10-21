#!/usr/bin/env python3
"""
S3 Processor Lambda - Simplified version that triggers RAG-Anything ECS task for document processing
"""
import json
import os
import boto3
import time

def lambda_handler(event, context):
    """Handle S3 document upload events"""
    try:
        # Parse S3 event
        for record in event['Records']:
            bucket = record['s3']['bucket']['name']
            key = record['s3']['object']['key']
            
            print(f"Processing document: s3://{bucket}/{key}")
            
            # Initialize ECS client
            ecs_client = boto3.client('ecs')
            
            try:
                # Run RAG-Anything task with document info as environment variables
                print("Starting RAG-Anything task for document processing...")
                response = ecs_client.run_task(
                    cluster=os.environ['ECS_CLUSTER'],
                    taskDefinition=os.environ['RAGANYTHING_TASK_DEFINITION'],
                    capacityProviderStrategy=[
                        {
                            'capacityProvider': 'FARGATE_SPOT',
                            'weight': 3
                        },
                        {
                            'capacityProvider': 'FARGATE',
                            'weight': 1
                        }
                    ],
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
                                    {'name': 'S3_BUCKET', 'value': bucket},
                                    {'name': 'S3_KEY', 'value': key},
                                    {'name': 'MODE', 'value': 'process_document'}
                                ]
                            }
                        ]
                    }
                )
                
                task_arn = response['tasks'][0]['taskArn']
                print(f"RAG-Anything task started: {task_arn}")
                
                # Wait for task to complete (with timeout)
                print("Waiting for task completion...")
                waiter = ecs_client.get_waiter('tasks_stopped')
                waiter.wait(
                    cluster=os.environ['ECS_CLUSTER'],
                    tasks=[task_arn],
                    WaiterConfig={
                        'Delay': 15,
                        'MaxAttempts': 80  # 20 minutes max for document processing
                    }
                )
                
                # Get task results
                task_details = ecs_client.describe_tasks(
                    cluster=os.environ['ECS_CLUSTER'],
                    tasks=[task_arn]
                )
                
                task = task_details['tasks'][0]
                exit_code = task['containers'][0].get('exitCode', -1)
                
                if exit_code == 0:
                    print(f"Document processing completed successfully for s3://{bucket}/{key}")
                else:
                    print(f"Document processing failed with exit code: {exit_code} for s3://{bucket}/{key}")
                
            except Exception as e:
                print(f"Error processing document s3://{bucket}/{key}: {str(e)}")
                continue
                
    except Exception as e:
        print(f"Error processing S3 event: {str(e)}")
        return {
            'statusCode': 500,
            'body': json.dumps({'error': str(e)})
        }
    
    return {
        'statusCode': 200,
        'body': json.dumps({'message': 'Document processing completed'})
    }