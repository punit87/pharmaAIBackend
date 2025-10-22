import json
import boto3
import os
import requests
import time

def lambda_handler(event, context):
    try:
        # Handle S3 event (from S3 notification)
        if 'Records' in event:
            # Extract S3 event information
            record = event['Records'][0]
            bucket_name = record['s3']['bucket']['name']
            document_key = record['s3']['object']['key']
            document_name = document_key.split('/')[-1]  # Get filename from key
            
            print(f"Processing S3 event: bucket={bucket_name}, key={document_key}")
        else:
            # Handle API Gateway event (for manual testing)
            if 'body' in event:
                body = json.loads(event['body'])
                document_key = body.get('document_key', '')
                document_name = body.get('document_name', '')
            else:
                document_key = event.get('document_key', '')
                document_name = event.get('document_name', '')

        if not document_key:
            return {
                'statusCode': 400,
                'headers': {
                    'Content-Type': 'application/json',
                    'Access-Control-Allow-Origin': '*'
                },
                'body': json.dumps({'error': 'No document_key provided'})
            }

        print(f"Processing document: {document_key}")
        if document_name:
            print(f"Document name: {document_name}")

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
                        break
            
            # If we found a PENDING task, wait for it to become RUNNING
            if task_arn:
                task_details = ecs_client.describe_tasks(
                    cluster=os.environ['ECS_CLUSTER'],
                    tasks=[task_arn]
                )
                task = task_details['tasks'][0]
                
                if task['lastStatus'] == 'PENDING':
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
                        print(f"Task {task_arn} is now RUNNING")
                    except Exception as e:
                        print(f"Error waiting for task {task_arn} to start: {str(e)}")
                        task_arn = None
            
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
                    print(f"Task {task_arn} is now RUNNING")
                    
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
            
            # Use ALB endpoint instead of direct IP
            alb_endpoint = os.environ['ALB_ENDPOINT']
            server_url = f"http://{alb_endpoint}"
            process_url = f"{server_url}/process"
            
            print(f"Making document processing request to ALB: {process_url}")
            
            # Wait a bit for the ALB to register the task as healthy
            print("Waiting for ALB health check to pass...")
            time.sleep(30)  # Give ALB time to register the task
            
            # Prepare request payload
            payload = {'document_key': document_key}
            if document_name:
                payload['document_name'] = document_name
            
            process_response = requests.post(
                process_url,
                json=payload,
                headers={'Content-Type': 'application/json'},
                timeout=300  # 5 minutes timeout
            )
            
            if process_response.status_code == 200:
                result = process_response.json()
                print("Document processed successfully")
                
                # Stop the task after processing to save costs
                try:
                    print(f"Stopping task {task_arn} to save costs...")
                    ecs_client.stop_task(
                        cluster=os.environ['ECS_CLUSTER'],
                        task=task_arn,
                        reason='Document processing completed - stopping to save costs'
                    )
                    print("Task stopped successfully")
                except Exception as e:
                    print(f"Warning: Could not stop task: {str(e)}")
            
                # Return appropriate response based on event type
                if 'Records' in event:
                    # S3 event - just log success
                    print(f"Document processing completed successfully: {document_key}")
                    return {'status': 'success', 'document_key': document_key}
                else:
                    # API Gateway event - return HTTP response
                    return {
                        'statusCode': 200,
                        'headers': {
                            'Content-Type': 'application/json',
                            'Access-Control-Allow-Origin': '*'
                        },
                        'body': json.dumps({
                            'status': 'success',
                            'message': 'Document processed successfully.',
                            'document_key': document_key,
                            'document_name': document_name,
                            'result': result,
                            'task_arn': task_arn
                        })
                    }
            else:
                print(f"Document processing failed with status: {process_response.status_code}")
                if 'Records' in event:
                    # S3 event - just log error
                    print(f"Document processing failed: {process_response.text}")
                    return {'status': 'error', 'document_key': document_key, 'error': process_response.text}
                else:
                    # API Gateway event - return HTTP error response
                    return {
                        'statusCode': 500,
                        'headers': {
                            'Content-Type': 'application/json',
                            'Access-Control-Allow-Origin': '*'
                        },
                        'body': json.dumps({
                            'error': f'Document processing failed: {process_response.text}',
                            'task_arn': task_arn
                        })
                    }

        except Exception as e:
            print(f"Error running RAG-Anything task: {str(e)}")
            if 'Records' in event:
                # S3 event - just log error
                print(f"Error processing document: {str(e)}")
                return {'status': 'error', 'error': str(e)}
            else:
                # API Gateway event - return HTTP error response
                return {
                    'statusCode': 500,
                    'headers': {
                        'Content-Type': 'application/json',
                        'Access-Control-Allow-Origin': '*'
                    },
                    'body': json.dumps({'error': f'Error running RAG-Anything task: {str(e)}'})
                }

    except Exception as e:
        print(f"Error processing document: {str(e)}")
        if 'Records' in event:
            # S3 event - just log error
            return {'status': 'error', 'error': str(e)}
        else:
            # API Gateway event - return HTTP error response
            return {
                'statusCode': 500,
                'headers': {
                    'Content-Type': 'application/json',
                    'Access-Control-Allow-Origin': '*'
                },
                'body': json.dumps({'error': str(e)})
            }
