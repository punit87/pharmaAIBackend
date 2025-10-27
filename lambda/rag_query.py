import json
import boto3
import os
import requests
import time
import socket

def lambda_handler(event, context):
    # Handle CORS preflight OPTIONS request
    if event.get('httpMethod') == 'OPTIONS':
        return {
            'statusCode': 200,
            'headers': {
                'Access-Control-Allow-Origin': '*',
                'Access-Control-Allow-Methods': 'OPTIONS, POST',
                'Access-Control-Allow-Headers': 'Content-Type',
                'Access-Control-Max-Age': '86400'
            },
            'body': ''
        }
    
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

        # Use ALB endpoint for reliable connection to ECS tasks
        alb_endpoint = os.environ.get('ALB_ENDPOINT')
        if not alb_endpoint:
            print("ALB_ENDPOINT not configured")
            return {
                'statusCode': 500,
                'headers': {
                    'Content-Type': 'application/json',
                    'Access-Control-Allow-Origin': '*'
                },
                'body': json.dumps({'error': 'ALB endpoint not configured'})
            }
        
        server_url = f"http://{alb_endpoint}"
        query_url = f"{server_url}/query"
        
        print(f"Making query request via ALB: {query_url}")

        # Retry logic with exponential backoff
        max_retries = 5
        retry_delay = 5  # Start with 5 seconds
        query_response = None
        
        for attempt in range(max_retries):
            start_time = time.time()
            try:
                print(f"Attempt {attempt + 1}/{max_retries}: Making query request to ALB: {query_url}")
                print(f"Lambda is in VPC: {os.environ.get('AWS_LAMBDA_FUNCTION_NAME')}")
                print(f"Query payload: {json.dumps({'query': query})}")
                
                # Test DNS resolution first
                print(f"Testing DNS resolution for ALB: {alb_endpoint}")
                try:
                    ip = socket.gethostbyname(alb_endpoint)
                    print(f"DNS resolved to: {ip}")
                except Exception as dns_error:
                    print(f"DNS resolution failed: {str(dns_error)}")
                    raise
                
                # Try with shorter timeout first to fail fast
                connect_timeout = 30  # Connection timeout
                read_timeout = 270   # Read timeout (5 mins - 30 secs)
                
                print(f"Making HTTP request with connect_timeout={connect_timeout}s, read_timeout={read_timeout}s")
                
                query_response = requests.post(
                    query_url,
                    json={'query': query},
                    headers={'Content-Type': 'application/json'},
                    timeout=(connect_timeout, read_timeout)  # (connect, read) timeout tuple
                )
                elapsed = time.time() - start_time
                print(f"Request completed in {elapsed:.2f}s with status {query_response.status_code}")
                
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
                    
            except requests.exceptions.Timeout as e:
                elapsed = time.time() - start_time
                print(f"Request timeout on attempt {attempt + 1}: {str(e)}")
                print(f"Timeout occurred after {elapsed:.2f}s")
                if attempt < max_retries - 1:
                    time.sleep(retry_delay)
                    retry_delay *= 2
                    continue
            except requests.exceptions.ConnectionError as e:
                elapsed = time.time() - start_time
                print(f"Connection error on attempt {attempt + 1}: {str(e)}")
                print(f"Connection failed after {elapsed:.2f}s")
                if attempt < max_retries - 1:
                    time.sleep(retry_delay)
                    retry_delay *= 2
                    continue
            except Exception as e:
                elapsed = time.time() - start_time
                print(f"Unexpected error on attempt {attempt + 1}: {str(e)}")
                print(f"Exception type: {type(e).__name__}")
                print(f"Error occurred after {elapsed:.2f}s")
                if attempt < max_retries - 1:
                    time.sleep(retry_delay)
                    retry_delay *= 2
                    continue
        
        if query_response and query_response.status_code == 200:
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
        elif query_response:
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
        else:
            print("All retry attempts failed - could not connect to ALB")
            return {
                'statusCode': 500,
                'headers': {
                    'Content-Type': 'application/json',
                    'Access-Control-Allow-Origin': '*'
                },
                'body': json.dumps({
                    'error': 'Failed to connect to RAG service after multiple attempts. Please try again.'
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