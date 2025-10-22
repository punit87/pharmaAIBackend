import json
import boto3
import os
import requests

def lambda_handler(event, context):
    try:
        # Parse S3 event
        if 'Records' in event:
            record = event['Records'][0]
            bucket = record['s3']['bucket']['name']
            key = record['s3']['object']['key']
        else:
            bucket = event.get('bucket', '')
            key = event.get('key', '')

        if not bucket or not key:
            return {
                'statusCode': 400,
                'body': json.dumps({'error': 'Missing bucket or key'})
            }

        print(f"Processing document: s3://{bucket}/{key}")

        # Initialize ECS client
        ecs_client = boto3.client('ecs')
        
        try:
            # Start RAG-Anything task in server mode
            print("Starting RAG-Anything server task for document processing...")
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
                return {
                    'statusCode': 500,
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
                    'body': json.dumps({'error': 'Could not get server IP address'})
                }
            
            # Make HTTP request to the server
            server_url = f"http://{private_ip}:8000"
            process_url = f"{server_url}/process"
            
            print(f"Making process request to: {process_url}")
            process_response = requests.post(
                process_url,
                json={'bucket': bucket, 'key': key},
                headers={'Content-Type': 'application/json'},
                timeout=600  # 10 minutes timeout
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
                
                return {
                    'statusCode': 200,
                    'body': json.dumps({
                        'message': 'Document processing completed',
                        'result': result,
                        'task_arn': task_arn
                    })
                }
            else:
                print(f"Document processing failed with status: {process_response.status_code}")
                return {
                    'statusCode': 500,
                    'body': json.dumps({
                        'error': f'Document processing failed: {process_response.text}',
                        'task_arn': task_arn
                    })
                }

        except Exception as e:
            print(f"Error running RAG-Anything task: {str(e)}")
            return {
                'statusCode': 500,
                'body': json.dumps({'error': f'Error running RAG-Anything task: {str(e)}'})
            }

    except Exception as e:
        print(f"Error processing document: {str(e)}")
        return {
            'statusCode': 500,
            'body': json.dumps({'error': str(e)})
        }
