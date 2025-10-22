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
            process_url = f"{server_url}/process"
            
            print(f"Making document processing request to ECS task: {process_url}")
            
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
                print(f"Attempt {attempt + 1}/{max_retries}: Making document processing request to ALB: {process_url}")
                
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
                    break  # Success, exit retry loop
                elif process_response.status_code == 502 or process_response.status_code == 503:
                    # ALB/task not ready, retry
                    if attempt < max_retries - 1:
                        print(f"ALB returned {process_response.status_code}, retrying in {retry_delay} seconds...")
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
        
        if process_response.status_code == 200:
            result = process_response.json()
            print("Document processed successfully")
            
            # Task stays running for better performance (DesiredCount=1)
            print("ECS task remains running for better performance")
            
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
                        'result': result
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
                        'error': f'Document processing failed: {process_response.text}'
                    })
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