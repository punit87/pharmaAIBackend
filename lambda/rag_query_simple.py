#!/usr/bin/env python3
"""
RAG Query Lambda - Simplified version that directly triggers RAG-Anything for query processing
"""
import json
import os
import boto3
import time
import requests

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
        
        # Start RAG-Anything service if not running
        raganything_ip = None
        try:
            # Check if RAG-Anything is already running
            running_tasks = ecs_client.list_tasks(
                cluster=os.environ['ECS_CLUSTER'],
                desiredStatus='RUNNING'
            )
            
            if running_tasks['taskArns']:
                task_details = ecs_client.describe_tasks(
                    cluster=os.environ['ECS_CLUSTER'],
                    tasks=running_tasks['taskArns']
                )
                
                for task in task_details['tasks']:
                    if 'raganything' in task['taskDefinitionArn']:
                        # Get task IP
                        for attachment in task.get('attachments', []):
                            for detail in attachment.get('details', []):
                                if detail['name'] == 'networkInterfaceId':
                                    eni_id = detail['value']
                                    ec2_client = boto3.client('ec2')
                                    eni_response = ec2_client.describe_network_interfaces(
                                        NetworkInterfaceIds=[eni_id]
                                    )
                                    raganything_ip = eni_response['NetworkInterfaces'][0]['PrivateIpAddress']
                                    break
                            if raganything_ip:
                                break
                        break
            
            if not raganything_ip:
                print("Starting RAG-Anything container...")
                raganything_response = ecs_client.run_task(
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
                
                # Wait for RAG-Anything to be running
                raganything_task_arn = raganything_response['tasks'][0]['taskArn']
                print(f"Waiting for RAG-Anything task {raganything_task_arn} to be running...")
                
                waiter = ecs_client.get_waiter('tasks_running')
                waiter.wait(
                    cluster=os.environ['ECS_CLUSTER'],
                    tasks=[raganything_task_arn]
                )
                
                # Get RAG-Anything IP
                task_details = ecs_client.describe_tasks(
                    cluster=os.environ['ECS_CLUSTER'],
                    tasks=[raganything_task_arn]
                )
                
                for attachment in task_details['tasks'][0].get('attachments', []):
                    for detail in attachment.get('details', []):
                        if detail['name'] == 'networkInterfaceId':
                            eni_id = detail['value']
                            ec2_client = boto3.client('ec2')
                            eni_response = ec2_client.describe_network_interfaces(
                                NetworkInterfaceIds=[eni_id]
                            )
                            raganything_ip = eni_response['NetworkInterfaces'][0]['PrivateIpAddress']
                            break
                    if raganything_ip:
                        break
                
                print(f"RAG-Anything container started with IP: {raganything_ip}")
            
        except Exception as e:
            print(f"Error starting RAG-Anything: {str(e)}")
            return {
                'statusCode': 500,
                'headers': {
                    'Content-Type': 'application/json',
                    'Access-Control-Allow-Origin': '*'
                },
                'body': json.dumps({'error': f'Error starting RAG-Anything: {str(e)}'})
            }
        
        # Now call the Flask endpoint to process the query
        raganything_url = f"http://{raganything_ip}:8000"
        query_url = f"{raganything_url}/query"
        
        print(f"Calling RAG-Anything Flask endpoint: {query_url}")
        
        payload = {
            'query': query
        }
        
        try:
            response = requests.post(query_url, json=payload, timeout=300)
            response.raise_for_status()
            
            result = response.json()
            print(f"Query processing result: {result}")
            
            return {
                'statusCode': 200,
                'headers': {
                    'Content-Type': 'application/json',
                    'Access-Control-Allow-Origin': '*'
                },
                'body': json.dumps(result)
            }
            
        except Exception as e:
            print(f"Error calling RAG-Anything endpoint: {str(e)}")
            return {
                'statusCode': 500,
                'headers': {
                    'Content-Type': 'application/json',
                    'Access-Control-Allow-Origin': '*'
                },
                'body': json.dumps({'error': f'Error processing query: {str(e)}'})
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