import json
import boto3
import os
import time

def lambda_handler(event, context):
    try:
        # Parse the query from the event
        if 'body' in event:
            body = json.loads(event['body'])
            query = body.get('query', '')
            image_url = body.get('image_url', '')
        else:
            query = event.get('query', '')
            image_url = event.get('image_url', '')

        if not query:
            return {
                'statusCode': 400,
                'headers': {
                    'Content-Type': 'application/json',
                    'Access-Control-Allow-Origin': '*'
                },
                'body': json.dumps({'error': 'No query provided'})
            }

        print(f"Processing multimodal query: {query}")
        if image_url:
            print(f"Image URL: {image_url}")

        # Initialize ECS client
        ecs_client = boto3.client('ecs')

        try:
            # Run RAG-Anything task in server mode
            print("Starting RAG-Anything server task for multimodal query...")
            response = ecs_client.run_task(
                cluster=os.environ['ECS_CLUSTER'],
                taskDefinition=os.environ['RAGANYTHING_TASK_DEFINITION'],
                capacityProviderStrategy=[
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
                                {'name': 'IMAGE_URL', 'value': image_url}
                            ]
                        }
                    ]
                }
            )

            task_arn = response['tasks'][0]['taskArn']
            print(f"RAG-Anything multimodal task started: {task_arn}")

            # Wait for task to be running
            print("Waiting for server to start...")
            waiter = ecs_client.get_waiter('tasks_running')
            waiter.wait(
                cluster=os.environ['ECS_CLUSTER'],
                tasks=[task_arn],
                WaiterConfig={
                    'Delay': 10,
                    'MaxAttempts': 30  # 5 minutes max to start
                }
            )

            # Get task details to find the private IP
            task_details = ecs_client.describe_tasks(
                cluster=os.environ['ECS_CLUSTER'],
                tasks=[task_arn]
            )

            task = task_details['tasks'][0]
            if task['lastStatus'] != 'RUNNING':
                return {
                    'statusCode': 500,
                    'headers': {
                        'Content-Type': 'application/json',
                        'Access-Control-Allow-Origin': '*'
                    },
                    'body': json.dumps({'error': 'Server failed to start'})
                }

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
                return {
                    'statusCode': 500,
                    'headers': {
                        'Content-Type': 'application/json',
                        'Access-Control-Allow-Origin': '*'
                    },
                    'body': json.dumps({'error': 'Could not get server IP address'})
                }

            # Make HTTP request to the server
            import requests
            server_url = f"http://{private_ip}:8000"
            query_url = f"{server_url}/query_multimodal"

            print(f"Making multimodal query request to: {query_url}")
            query_data = {'query': query}
            if image_url:
                query_data['image_url'] = image_url
                
            query_response = requests.post(
                query_url,
                json=query_data,
                headers={'Content-Type': 'application/json'},
                timeout=300  # 5 minutes timeout
            )

            if query_response.status_code == 200:
                result = query_response.json()
                print("Multimodal query processed successfully")
                return {
                    'statusCode': 200,
                    'headers': {
                        'Content-Type': 'application/json',
                        'Access-Control-Allow-Origin': '*'
                    },
                    'body': json.dumps({
                        'status': 'success',
                        'query': query,
                        'image_url': image_url,
                        'result': result,
                        'task_arn': task_arn
                    })
                }
            else:
                print(f"Multimodal query failed with status: {query_response.status_code}")
                return {
                    'statusCode': 500,
                    'headers': {
                        'Content-Type': 'application/json',
                        'Access-Control-Allow-Origin': '*'
                    },
                    'body': json.dumps({
                        'error': f'Multimodal query failed: {query_response.text}',
                        'task_arn': task_arn
                    })
                }

        except Exception as e:
            print(f"Error running RAG-Anything multimodal task: {str(e)}")
            return {
                'statusCode': 500,
                'headers': {
                    'Content-Type': 'application/json',
                    'Access-Control-Allow-Origin': '*'
                },
                'body': json.dumps({'error': f'Error running RAG-Anything multimodal task: {str(e)}'})
            }

    except Exception as e:
        return {
            'statusCode': 500,
            'headers': {
                'Content-Type': 'application/json',
                'Access-Control-Allow-Origin': '*'
            },
            'body': json.dumps({'error': str(e)})
        }
