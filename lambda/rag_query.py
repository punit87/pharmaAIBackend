import json
import boto3
import os
import requests

def lambda_handler(event, context):
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
            # Find existing running tasks first
            print("Looking for existing RAG-Anything server...")
            response = ecs_client.list_tasks(
                cluster=os.environ['ECS_CLUSTER'],
                desiredStatus='RUNNING'
            )
            
            # Also check for PENDING tasks (ECS status reporting can be delayed)
            pending_response = ecs_client.list_tasks(
                cluster=os.environ['ECS_CLUSTER'],
                desiredStatus='PENDING'
            )
            
            task_arn = None
            private_ip = None
            
            # Combine both RUNNING and PENDING task ARNs
            all_task_arns = response['taskArns'] + pending_response['taskArns']
            
            if all_task_arns:
                # Get details of all tasks
                task_details = ecs_client.describe_tasks(
                    cluster=os.environ['ECS_CLUSTER'],
                    tasks=all_task_arns
                )
                
                for task in task_details['tasks']:
                    # Accept both RUNNING and PENDING tasks (ECS status can be delayed)
                    if task['lastStatus'] in ['RUNNING', 'PENDING']:
                        task_arn = task['taskArn']
                        print(f"Found existing task: {task_arn} (status: {task['lastStatus']})")
                        
                        # Get private IP from task attachments (only if RUNNING)
                        if task['lastStatus'] == 'RUNNING':
                            for attachment in task['attachments']:
                                if attachment['type'] == 'ElasticNetworkInterface':
                                    for detail in attachment['details']:
                                        if detail['name'] == 'privateIPv4Address':
                                            private_ip = detail['value']
                                            break
                                    if private_ip:
                                        break
                        break
            
            # If we found a PENDING task, wait for it to become RUNNING
            if task_arn and not private_ip:
                print(f"Found PENDING task {task_arn}, waiting for it to become RUNNING...")
                try:
                    waiter = ecs_client.get_waiter('tasks_running')
                    waiter.wait(
                        cluster=os.environ['ECS_CLUSTER'],
                        tasks=[task_arn],
                        WaiterConfig={
                            'Delay': 10,
                            'MaxAttempts': 30  # 5 minutes max to start
                        }
                    )
                    
                    # Get updated task details to find the private IP
                    task_details = ecs_client.describe_tasks(
                        cluster=os.environ['ECS_CLUSTER'],
                        tasks=[task_arn]
                    )
                    
                    task = task_details['tasks'][0]
                    if task['lastStatus'] == 'RUNNING':
                        # Get private IP from task attachments
                        for attachment in task['attachments']:
                            if attachment['type'] == 'ElasticNetworkInterface':
                                for detail in attachment['details']:
                                    if detail['name'] == 'privateIPv4Address':
                                        private_ip = detail['value']
                                        break
                                if private_ip:
                                    break
                    else:
                        print(f"Task {task_arn} failed to start, status: {task['lastStatus']}")
                        task_arn = None
                        private_ip = None
                except Exception as e:
                    print(f"Error waiting for task {task_arn} to start: {str(e)}")
                    task_arn = None
                    private_ip = None
            
            if not task_arn:
                # Start new RAG-Anything server task
                print("No existing task found, starting new RAG-Anything server task...")
                try:
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
            
            # Make HTTP request to the server
            server_url = f"http://{private_ip}:8000"
            query_url = f"{server_url}/query"
            
            print(f"Making query request to: {query_url}")
            query_response = requests.post(
                query_url,
                json={'query': query},
                headers={'Content-Type': 'application/json'},
                timeout=300  # 5 minutes timeout
            )
            
            if query_response.status_code == 200:
                result = query_response.json()
                print("Query processed successfully")
                
                # Stop the task after processing to save costs
                try:
                    print(f"Stopping task {task_arn} to save costs...")
                    ecs_client.stop_task(
                        cluster=os.environ['ECS_CLUSTER'],
                        task=task_arn,
                        reason='Query processing completed - stopping to save costs'
                    )
                    print("Task stopped successfully")
                except Exception as e:
                    print(f"Warning: Could not stop task: {str(e)}")
            
                return {
                    'statusCode': 200,
                    'headers': {
                        'Content-Type': 'application/json',
                        'Access-Control-Allow-Origin': '*'
                    },
                    'body': json.dumps({
                        'status': 'success',
                        'message': 'Query processed successfully.',
                        'query': query,
                        'result': result,
                        'task_arn': task_arn
                    })
                }
            else:
                print(f"Query failed with status: {query_response.status_code}")
                return {
                    'statusCode': 500,
                    'headers': {
                        'Content-Type': 'application/json',
                        'Access-Control-Allow-Origin': '*'
                    },
                    'body': json.dumps({
                        'error': f'Query failed: {query_response.text}',
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
