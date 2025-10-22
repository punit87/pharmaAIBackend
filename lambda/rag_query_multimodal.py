import json
import boto3
import os
import requests
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

        # Find the running ECS task and use its IP directly
        ecs_client = boto3.client('ecs')
        
        try:
            # Find existing running tasks
            print("Looking for existing RAG-Anything server...")
            response = ecs_client.list_tasks(
                cluster=os.environ['ECS_CLUSTER'],
                desiredStatus='RUNNING'
            )
            
            if not response['taskArns']:
                print("No running tasks found - ECS service should maintain DesiredCount=1")
                return {
                    'statusCode': 503,
                    'headers': {
                        'Content-Type': 'application/json',
                        'Access-Control-Allow-Origin': '*'
                    },
                    'body': json.dumps({'error': 'No ECS tasks available. Service may be starting up.'})
                }
            
            # Get task details to find the IP
            task_details = ecs_client.describe_tasks(
                cluster=os.environ['ECS_CLUSTER'],
                tasks=response['taskArns']
            )
            
            task = task_details['tasks'][0]
            if task['lastStatus'] != 'RUNNING':
                print(f"Task status: {task['lastStatus']}")
                return {
                    'statusCode': 503,
                    'headers': {
                        'Content-Type': 'application/json',
                        'Access-Control-Allow-Origin': '*'
                    },
                    'body': json.dumps({'error': 'ECS task not running yet.'})
                }
            
            # Get the task's public IP
            task_arn = task['taskArn']
            attachments = task.get('attachments', [])
            if not attachments:
                print("No attachments found for task")
                return {
                    'statusCode': 503,
                    'headers': {
                        'Content-Type': 'application/json',
                        'Access-Control-Allow-Origin': '*'
                    },
                    'body': json.dumps({'error': 'Task has no network attachments.'})
                }
            
            # Find the public IP from the attachment details
            public_ip = None
            for attachment in attachments:
                for detail in attachment.get('details', []):
                    if detail['name'] == 'networkInterfaceId':
                        network_interface_id = detail['value']
                        ec2_client = boto3.client('ec2')
                        ni_response = ec2_client.describe_network_interfaces(
                            NetworkInterfaceIds=[network_interface_id]
                        )
                        public_ip = ni_response['NetworkInterfaces'][0]['Association']['PublicIp']
                        break
                if public_ip:
                    break
            
            if not public_ip:
                print("Could not find public IP for task")
                return {
                    'statusCode': 503,
                    'headers': {
                        'Content-Type': 'application/json',
                        'Access-Control-Allow-Origin': '*'
                    },
                    'body': json.dumps({'error': 'Could not find task public IP.'})
                }
            
            server_url = f"http://{public_ip}:8000"
            query_url = f"{server_url}/query-multimodal"
            
            print(f"Making multimodal query request to ECS task: {query_url}")
            
        except Exception as e:
            print(f"Error finding ECS task: {str(e)}")
            return {
                'statusCode': 500,
                'headers': {
                    'Content-Type': 'application/json',
                    'Access-Control-Allow-Origin': '*'
                },
                'body': json.dumps({'error': f'Error finding ECS task: {str(e)}'})
            }

        # Retry logic with exponential backoff
        max_retries = 5
        retry_delay = 10  # Start with 10 seconds
        
        for attempt in range(max_retries):
            try:
                print(f"Attempt {attempt + 1}/{max_retries}: Making multimodal query request to ALB: {query_url}")
                
                # Prepare request payload
                payload = {'query': query}
                if image_url:
                    payload['image_url'] = image_url
                
                query_response = requests.post(
                    query_url,
                    json=payload,
                    headers={'Content-Type': 'application/json'},
                    timeout=300  # 5 minutes timeout
                )
                
                if query_response.status_code == 200:
                    break  # Success, exit retry loop
                elif query_response.status_code == 502 or query_response.status_code == 503:
                    # ALB/task not ready, retry
                    if attempt < max_retries - 1:
                        print(f"ALB returned {query_response.status_code}, retrying in {retry_delay} seconds...")
                        time.sleep(retry_delay)
                        retry_delay *= 2  # Exponential backoff
                        continue
                else:
                    # Other error, don't retry
                    break
                    
            except requests.exceptions.Timeout:
                print(f"Request timeout on attempt {attempt + 1}")
                if attempt < max_retries - 1:
                    time.sleep(retry_delay)
                    retry_delay *= 2
                    continue
            except requests.exceptions.ConnectionError:
                print(f"Connection error on attempt {attempt + 1}")
                if attempt < max_retries - 1:
                    time.sleep(retry_delay)
                    retry_delay *= 2
                    continue
            except Exception as e:
                print(f"Unexpected error on attempt {attempt + 1}: {str(e)}")
                if attempt < max_retries - 1:
                    time.sleep(retry_delay)
                    retry_delay *= 2
                    continue
        
        if query_response.status_code == 200:
            result = query_response.json()
            print("Multimodal query processed successfully")
            
            # Task stays running for better performance (DesiredCount=1)
            print("ECS task remains running for better performance")
            
            return {
                'statusCode': 200,
                'headers': {
                    'Content-Type': 'application/json',
                    'Access-Control-Allow-Origin': '*'
                },
                'body': json.dumps({
                    'status': 'success',
                    'message': 'Multimodal query processed successfully.',
                    'query': query,
                    'image_url': image_url,
                    'result': result
                })
            }
        else:
            print(f"Multimodal query processing failed with status: {query_response.status_code}")
            return {
                'statusCode': 500,
                'headers': {
                    'Content-Type': 'application/json',
                    'Access-Control-Allow-Origin': '*'
                },
                'body': json.dumps({
                    'error': f'Multimodal query processing failed: {query_response.text}'
                })
            }
                
    except Exception as e:
        print(f"Error processing multimodal query: {str(e)}")
        return {
            'statusCode': 500,
            'headers': {
                'Content-Type': 'application/json',
                'Access-Control-Allow-Origin': '*'
            },
            'body': json.dumps({'error': str(e)})
        }