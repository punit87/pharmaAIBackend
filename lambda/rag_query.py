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

        # Use ALB endpoint - ECS service maintains DesiredCount=1
        alb_endpoint = os.environ['ALB_ENDPOINT']
        server_url = f"http://{alb_endpoint}"
        query_url = f"{server_url}/query"
        
        print(f"Making query request to ALB: {query_url}")
        
        # Wait for ALB health check to pass
        print("Waiting for ALB health check to pass...")
        time.sleep(120)  # Give ALB more time to register the task
        
        # Check if ALB target group has healthy targets
        print("Checking ALB target group health...")
        try:
            elb_client = boto3.client('elbv2')
            target_groups = elb_client.describe_target_groups(
                Names=[f'pharma-ecs-tg-{os.environ.get("Environment", "dev")}-v2']
            )
            if target_groups['TargetGroups']:
                target_group_arn = target_groups['TargetGroups'][0]['TargetGroupArn']
                targets = elb_client.describe_target_health(TargetGroupArn=target_group_arn)
                healthy_targets = [t for t in targets['TargetHealthDescriptions'] if t['TargetHealth']['State'] == 'healthy']
                print(f"Found {len(healthy_targets)} healthy targets in ALB target group")
                if not healthy_targets:
                    print("Warning: No healthy targets found in ALB target group")
        except Exception as e:
            print(f"Could not check ALB target group health: {str(e)}")

        # Retry logic with exponential backoff
        max_retries = 5
        retry_delay = 10  # Start with 10 seconds
        
        for attempt in range(max_retries):
            try:
                print(f"Attempt {attempt + 1}/{max_retries}: Making query request to ALB: {query_url}")
                query_response = requests.post(
                    query_url,
                    json={'query': query},
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
            print("Query processed successfully")
            
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
                    'message': 'Query processed successfully.',
                    'query': query,
                    'result': result
                })
            }
        else:
            print(f"Query processing failed with status: {query_response.status_code}")
            return {
                'statusCode': 500,
                'headers': {
                    'Content-Type': 'application/json',
                    'Access-Control-Allow-Origin': '*'
                },
                'body': json.dumps({
                    'error': f'Query processing failed: {query_response.text}'
                })
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