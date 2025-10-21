#!/usr/bin/env python3
"""
RAG Query Lambda - Simplified version that directly triggers RAG-Anything
"""
import json
import os
import boto3
import time

def lambda_handler(event, context):
    """Handle RAG query requests"""
    try:
        # Parse the request
        if 'body' in event:
            body = json.loads(event['body'])
        else:
            body = event
        
        query = body.get('query', '')
        if not query:
            return {
                'statusCode': 400,
                'headers': {
                    'Content-Type': 'application/json',
                    'Access-Control-Allow-Origin': '*'
                },
                'body': json.dumps({'error': 'Query is required'})
            }
        
        print(f"Processing RAG query: {query}")
        
        # Initialize ECS client
        ecs_client = boto3.client('ecs')
        
        # First, start Docling service if not running
        docling_ip = None
        try:
            # Check if Docling is already running
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
                    if 'docling' in task['taskDefinitionArn']:
                        # Get task IP
                        for attachment in task.get('attachments', []):
                            for detail in attachment.get('details', []):
                                if detail['name'] == 'networkInterfaceId':
                                    eni_id = detail['value']
                                    ec2_client = boto3.client('ec2')
                                    eni_response = ec2_client.describe_network_interfaces(
                                        NetworkInterfaceIds=[eni_id]
                                    )
                                    docling_ip = eni_response['NetworkInterfaces'][0]['PrivateIpAddress']
                                    break
                            if docling_ip:
                                break
                        break
        except Exception as e:
            print(f"Error checking for running Docling tasks: {str(e)}")
        
        # Start Docling if not running
        if not docling_ip:
            print("Starting Docling service...")
            docling_response = ecs_client.run_task(
                cluster=os.environ['ECS_CLUSTER'],
                taskDefinition=os.environ['DOCLING_TASK_DEFINITION'],
                launchType='FARGATE',
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
            
            if not docling_response['tasks']:
                return {
                    'statusCode': 500,
                    'headers': {
                        'Content-Type': 'application/json',
                        'Access-Control-Allow-Origin': '*'
                    },
                    'body': json.dumps({'error': 'Failed to start Docling service'})
                }
            
            # Wait for Docling to be ready
            docling_task_arn = docling_response['tasks'][0]['taskArn']
            max_wait_time = 120  # 2 minutes
            start_time = time.time()
            
            while time.time() - start_time < max_wait_time:
                task_response = ecs_client.describe_tasks(
                    cluster=os.environ['ECS_CLUSTER'],
                    tasks=[docling_task_arn]
                )
                
                task = task_response['tasks'][0]
                last_status = task['lastStatus']
                
                if last_status == 'RUNNING':
                    # Get task IP
                    for attachment in task.get('attachments', []):
                        for detail in attachment.get('details', []):
                            if detail['name'] == 'networkInterfaceId':
                                eni_id = detail['value']
                                ec2_client = boto3.client('ec2')
                                eni_response = ec2_client.describe_network_interfaces(
                                    NetworkInterfaceIds=[eni_id]
                                )
                                docling_ip = eni_response['NetworkInterfaces'][0]['PrivateIpAddress']
                                break
                        if docling_ip:
                            break
                    
                    if docling_ip:
                        break
                
                time.sleep(5)
            
            if not docling_ip:
                return {
                    'statusCode': 500,
                    'headers': {
                        'Content-Type': 'application/json',
                        'Access-Control-Allow-Origin': '*'
                    },
                    'body': json.dumps({'error': 'Docling service failed to start within timeout'})
                }
        
        print(f"Docling service running at: {docling_ip}")
        
        # Start RAG-Anything container as a persistent service
        print("Starting RAG-Anything container as persistent service...")
        response = ecs_client.run_task(
            cluster=os.environ['ECS_CLUSTER'],
            taskDefinition=os.environ['RAGANYTHING_TASK_DEFINITION'],
            launchType='FARGATE',
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
                            {'name': 'AWS_DEFAULT_REGION', 'value': os.environ.get('AWS_DEFAULT_REGION', 'us-east-1')},
                            {'name': 'NEO4J_URI', 'value': os.environ['NEO4J_URI']},
                            {'name': 'NEO4J_USERNAME', 'value': os.environ['NEO4J_USERNAME']},
                            {'name': 'NEO4J_PASSWORD', 'value': os.environ['NEO4J_PASSWORD']},
                            {'name': 'OPENAI_API_KEY', 'value': os.environ['OPENAI_API_KEY']},
                            {'name': 'DOCLING_SERVICE_URL', 'value': f'http://{docling_ip}:8000'}
                        ]
                    }
                ]
            }
        )
        
        if not response['tasks']:
            return {
                'statusCode': 500,
                'headers': {
                    'Content-Type': 'application/json',
                    'Access-Control-Allow-Origin': '*'
                },
                'body': json.dumps({'error': 'Failed to start RAG-Anything container'})
            }
        
        task_arn = response['tasks'][0]['taskArn']
        print(f"Started RAG-Anything task: {task_arn}")
        
        # Wait for RAG-Anything container to be ready
        max_wait_time = 120  # 2 minutes
        start_time = time.time()
        raganything_ip = None
        
        while time.time() - start_time < max_wait_time:
            task_response = ecs_client.describe_tasks(
                cluster=os.environ['ECS_CLUSTER'],
                tasks=[task_arn]
            )
            
            task = task_response['tasks'][0]
            last_status = task['lastStatus']
            
            if last_status == 'RUNNING':
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
                
                if raganything_ip:
                    break
            
            time.sleep(5)
        
        if not raganything_ip:
            return {
                'statusCode': 500,
                'headers': {
                    'Content-Type': 'application/json',
                    'Access-Control-Allow-Origin': '*'
                },
                'body': json.dumps({'error': 'RAG-Anything container failed to start within timeout'})
            }
        
        print(f"RAG-Anything service running at: {raganything_ip}")
        
        # Now call the Flask endpoint to process the query
        import requests
        
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
        print(f"Error processing RAG query: {str(e)}")
        return {
            'statusCode': 500,
            'headers': {
                'Content-Type': 'application/json',
                'Access-Control-Allow-Origin': '*'
            },
            'body': json.dumps({'error': str(e)})
        }
