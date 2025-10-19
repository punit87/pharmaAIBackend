import json
import os
import logging
import requests

# Set up logging
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

# Fetch the RAG training endpoint from environment variables
RAG_TRAIN_URL = os.getenv(" ")

if not RAG_TRAIN_URL:
    raise ValueError("RAG_TRAIN_URL environment variable is not set")

def add_cors(response):
    """Add CORS headers to the response."""
    response.setdefault("headers", {})
    response["headers"].update({
        "Access-Control-Allow-Origin": "*",
        "Access-Control-Allow-Methods": "OPTIONS,GET,POST",
        "Access-Control-Allow-Headers": "Content-Type"
    })
    return response

def lambda_handler(event, context):
    """AWS Lambda function to redirect POST request to RAG_TRAIN_URL and return response."""
    try:
       
        # Forward the request to RAG_TRAIN_URL
        headers = {"Content-Type": "application/json"}
        response = requests.get(RAG_TRAIN_URL, headers=headers)

        # Log the response
        logger.info(f"Received response: {response.status_code} - {response.text}")

        # Return the response back with CORS headers
        return add_cors({
            "statusCode": response.status_code,
            "body": response.text
        })

    except Exception as e:
        logger.error(f"An error occurred: {str(e)}", exc_info=True)
        return add_cors({
            "statusCode": 500,
            "body": json.dumps({"error": str(e)})
        })
