import json
import os
import logging
import requests
from time import sleep

# Set up logging
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

# Model names mapping
MODEL_NAMES = {
    "GPT-2": "openai-community/gpt2",
    "DeepSeek-R1-Distill-Qwen-1.5B": "deepseek-ai/DeepSeek-R1-Distill-Qwen-1.5B",
    "Llama-3.2-1B": "meta-llama/Llama-3.2-1B"
}

INFERENCE_API_URL =  os.getenv('INFERENCE_API_URL') 

def add_cors(response):
    """Add CORS headers to the response."""
    if "headers" not in response:
        response["headers"] = {}
    response["headers"].update({
        "Access-Control-Allow-Origin": "*",
        "Access-Control-Allow-Methods": "OPTIONS,GET,POST",
        "Access-Control-Allow-Headers": "Content-Type"
    })
    return response

def make_request_with_retries(url, headers, payload, retries=3, delay=5):
    """
    Make the HTTP POST request with retries in case of a timeout or other transient issues.
    """
    for attempt in range(retries):
        try:
            # Make the API request with a long timeout
            #response = requests.post(
                #url,
                #headers=headers,
                #json=payload,
                #timeout=(300, 1200)
            #)

            response = requests.post(
                f"{os.getenv("GOOGLE_COLAB_URL")}",
                headers=headers,
                json=data
            )

            # Check for successful response
            if response.status_code == 200:
                return response.json()
            else:
                logger.error(f"API request failed with status code {response.status_code}")
                return None
        except requests.exceptions.Timeout as e:
            logger.error(f"Timeout occurred on attempt {attempt + 1}/{retries}: {str(e)}")
        except requests.exceptions.RequestException as e:
            logger.error(f"Request failed on attempt {attempt + 1}/{retries}: {str(e)}")
        
        # Wait before retrying
        sleep(delay)
    
    # After retries, return None or an error message
    return None

def lambda_handler(event, context):
    """AWS Lambda function for invoking models via Hugging Face REST API."""
    try:
        # Parse the request body
        data = json.loads(event.get("body", "{}"))
        prompt = data.get('prompt', '')
        model_name = data.get('model_name', '')

        # Validate model name
        if model_name not in MODEL_NAMES:
            return add_cors({
                "statusCode": 400,
                "body": json.dumps({"error": "Model not found"})
            })

        # Prepare headers for the Hugging Face API request
        headers = {
            "Authorization": f"Bearer {os.getenv('HF_API_KEY')}",
            "Content-Type": "application/json"
        }

        # Prepare the payload for the request
        payload = {
            "inputs": prompt,
            "options": {"use_cache": False},
            "parameters": {
                "max_new_tokens": 1024,
                "temperature": 0.7,
                "top_p": 0.9
            }
        }

        # Make the API request to Hugging Face Inference API with retries
        response_json = make_request_with_retries(
            f"{INFERENCE_API_URL}/{MODEL_NAMES[model_name]}",
            headers,
            payload
        )

        if response_json:
            # Check if generated text exists and return it
            generated_text = response_json[0].get("generated_text", "")
            if generated_text:
                logger.info(f"Received response from Hugging Face model: {generated_text}")

                # Return the response with CORS headers
                return add_cors({
                    "statusCode": 200,
                    "body": json.dumps({"response": generated_text})
                })
            else:
                return add_cors({
                    "statusCode": 400,
                    "body": json.dumps({"error": "Generated text not found"})
                })
        else:
            return add_cors({
                "statusCode": 500,
                "body": json.dumps({"error": "Failed to generate response after retries"})
            })

    except Exception as e:
        # Handle exceptions and return an error response
        logger.error(f"An error occurred: {str(e)}", exc_info=True)
        return add_cors({
            "statusCode": 500,
            "body": json.dumps({"error": str(e)})
        })
