#!/usr/bin/env python3
"""
RAG Query Lambda - Simplified version that triggers RAG-Anything ECS task for query processing
"""
import json
import os
import boto3
import time

def lambda_handler(event, context):
    """Handle RAG query requests"""
    try:
        # Parse the query from the event
        if 'body' in event:
            body = json.loads(event['body'])
            query = body.get('query', '')
        else:
            query = event.get('query', '')
        
        if not query:
            return {
                'statusCode': 400,
                'headers': {
                    'Content-Type': 'application/json',
                    'Access-Control-Allow-Origin': '*'
                },
                'body': json.dumps({'error': 'No query provided'})
            }
        
        print(f"Processing query: {query}")
        
        # Initialize ECS client
        ecs_client = boto3.client('ecs')
        
        try:
            # Run RAG-Anything task with query as environment variable
            print("Starting RAG-Anything task for query processing...")
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
                                {'name': 'QUERY', 'value': query},
                                {'name': 'MODE', 'value': 'query_only'}
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
                    'Delay': 10,
                    'MaxAttempts': 60  # 10 minutes max
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
                print("Query processing completed successfully")
                return {
                    'statusCode': 200,
                    'headers': {
                        'Content-Type': 'application/json',
                        'Access-Control-Allow-Origin': '*'
                    },
                    'body': json.dumps({
                        'status': 'success',
                        'query': query,
                        'task_arn': task_arn,
                        'message': 'Query processed successfully. Check EFS output directory for results.'
                    })
                }
            else:
                print(f"Task failed with exit code: {exit_code}")
                return {
                    'statusCode': 500,
                    'headers': {
                        'Content-Type': 'application/json',
                        'Access-Control-Allow-Origin': '*'
                    },
                    'body': json.dumps({
                        'error': f'Query processing failed with exit code: {exit_code}',
                        'task_arn': task_arn
                    })
                }
                
        except Exception as e:
            print(f"Error running RAG-Anything task: {str(e)}")
            return {
                'statusCode': 500,
                'headers': {
                    'Content-Type': 'application/json',
                    'Access-Control-Allow-Origin': '*'
                },
                'body': json.dumps({'error': f'Error running RAG-Anything task: {str(e)}'})
            }
            
    except Exception as e:
        print(f"Error processing query: {str(e)}")
        return {
            'statusCode': 500,
            'headers': {
                'Content-Type': 'application/json',
                'Access-Control-Allow-Origin': '*'
            },
            'body': json.dumps({'error': str(e)})
        }