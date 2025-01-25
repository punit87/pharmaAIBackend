import json
import os
import logging
import requests

# Set up logging
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

# Model names mapping
MODEL_NAMES = {
    "GPT-2": "openai-community/gpt2",
    "T5": "google-t5/t5-small",
    "GPT-Neo": "EleutherAI/gpt-neo-2.7B",
    "BART": "facebook/bart-large",
}

HUGGINGFACE_API_URL = "https://api-inference.huggingface.co/models"

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
            "Authorization": f"Bearer {os.getenv('HF_API_KEY')}"  # API Key from environment variable
        }

        # Prepare the payload for the request
        if model_name == "T5":
            # For T5, we will create a specific prompt format
            input_text = f"question: {prompt} context: {prompt}"
            payload = {
                "inputs": input_text,
                "options": {"use_cache": False}
            }
        elif model_name == "BART":
            # For BART, we just pass the prompt directly
            payload = {
                "inputs": prompt,
                "options": {"use_cache": False}
            }
        else:
            # For GPT-2 and GPT-Neo, we pass the prompt directly
            payload = {
                "inputs": prompt,
                "options": {"use_cache": False}
            }

        # Make the API request to Hugging Face Inference API
        response = requests.post(
            f"{HUGGINGFACE_API_URL}/{MODEL_NAMES[model_name]}",
            headers=headers,
            json=payload
        )

        # Log the full response for debugging
        logger.debug(f"Response: {response.text}")

        if response.status_code == 200:
            # Parse the response JSON
            response_json = response.json()

            # Check if generated text exists and return it
            generated_text = response_json[0].get("generated_text", "")
            if generated_text:
                logger.info(f"Received response from Hugging Face model: {generated_text}")

                # Return the response with CORS headers
                return add_cors({
                    "statusCode": 200,
                    "body": json.dumps({
                        "response": generated_text
                    })
                })
            else:
                return add_cors({
                    "statusCode": 400,
                    "body": json.dumps({"error": "Generated text not found"})
                })
        else:
            logger.error(f"Hugging Face API request failed with status code {response.status_code}")
            return add_cors({
                "statusCode": response.status_code,
                "body": json.dumps({"error": "Failed to generate response"})
            })

    except Exception as e:
        # Handle exceptions and return an error response
        logger.error(f"An error occurred: {str(e)}", exc_info=True)
        return add_cors({
            "statusCode": 500,
            "body": json.dumps({"error": str(e)})
        })
