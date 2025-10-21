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
                # Run RAG-Anything task in server mode
                print("Starting RAG-Anything server task...")
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
                    }
                )
                
                task_arn = response['tasks'][0]['taskArn']
                print(f"RAG-Anything server task started: {task_arn}")
                
                # Wait for task to be running
                print("Waiting for server to start...")
                waiter = ecs_client.get_waiter('tasks_running')
                waiter.wait(
                    cluster=os.environ['ECS_CLUSTER'],
                    tasks=[task_arn],
                    WaiterConfig={
                        'Delay': 15,
                        'MaxAttempts': 40  # 10 minutes max to start
                    }
                )
                
                # Get task details to find the private IP
                task_details = ecs_client.describe_tasks(
                    cluster=os.environ['ECS_CLUSTER'],
                    tasks=[task_arn]
                )
                
                task = task_details['tasks'][0]
                if task['lastStatus'] != 'RUNNING':
                    print(f"Server failed to start for s3://{bucket}/{key}")
                    continue
                
                # Get private IP from network interfaces
                private_ip = None
                for container in task['containers']:
                    if 'networkInterfaces' in container:
                        for ni in container['networkInterfaces']:
                            private_ip = ni.get('privateIpv4Address')
                            break
                    if private_ip:
                        break
                
                if not private_ip:
                    print(f"Could not get server IP address for s3://{bucket}/{key}")
                    continue
                
                # Make HTTP request to the server
                import requests
                server_url = f"http://{private_ip}:8000"
                process_url = f"{server_url}/process"
                
                print(f"Making document processing request to: {process_url}")
                process_response = requests.post(
                    process_url,
                    json={
                        's3_bucket': bucket,
                        's3_key': key
                    },
                    headers={'Content-Type': 'application/json'},
                    timeout=600  # 10 minutes timeout for document processing
                )
                
                if process_response.status_code == 200:
                    result = process_response.json()
                    print(f"Document processing completed successfully for s3://{bucket}/{key}")
                    print(f"Processing result: {result}")
                else:
                    print(f"Document processing failed with status: {process_response.status_code} for s3://{bucket}/{key}")
                    print(f"Error: {process_response.text}")
                
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