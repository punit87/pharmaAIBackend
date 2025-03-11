import json
import os
import logging
import requests
from nltk.tokenize import sent_tokenize
from datetime import datetime

# Set up logging
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

# Ensure the NLTK data directory is set (for redundancy)
os.environ["NLTK_DATA"] = "/usr/share/nltk_data"

# Model names mapping
MODEL_NAMES = {
    "GPT-2": "openai-community/gpt2",
    "DeepSeek-R1-Distill-Qwen-1.5B": "deepseek-ai/DeepSeek-R1-Distill-Qwen-1.5B",
    "Llama-3.2-1B": "meta-llama/Llama-3.2-1B"
}

HUGGINGFACE_API_URL = "https://api-inference.huggingface.co/models"

def add_cors(response):
    """Add CORS headers to the response."""
    logger.debug("Adding CORS headers to the response.")
    if "headers" not in response:
        response["headers"] = {}
    response["headers"].update({
        "Access-Control-Allow-Origin": "*",
        "Access-Control-Allow-Methods": "OPTIONS,GET,POST",
        "Access-Control-Allow-Headers": "Content-Type",
        "Cache-Control": "no-cache, no-store, must-revalidate",  # Disable caching
        "Pragma": "no-cache",  # For older HTTP/1.0 caches
        "Expires": "0"  # Ensure that responses are not cached
    })
    logger.debug("CORS headers added successfully.")
    return response

def lambda_handler(event, context):
    """AWS Lambda function for generating section-specific content."""
    try:
        logger.info("Lambda function started.")
        
        # Parse the request body
        data = json.loads(event.get("body", "{}"))
        logger.debug(f"Received data: {data}")
        
        model_name = data.get('model_name', '')
        section_name = data.get('section_name', '')
        document_heading = data.get('document_heading', '')

        logger.info(f"Model Name: {model_name}, Section Name: {section_name}, Document Heading: {document_heading}")
        
        # Validate the model name
        if model_name not in MODEL_NAMES:
            logger.error(f"Model '{model_name}' not found in model mapping.")
            return add_cors({
                "statusCode": 400,
                "body": json.dumps({"error": "Model not found"})
            })
        
        logger.info(f"Model '{model_name}' is valid. Proceeding with content generation.")
        
        # Get the current timestamp for cache busting or logging
        timestamp = datetime.utcnow().isoformat()

        # Generate the prompt
        prompt = f'''
        section: {section_name}.
        '''

        logger.debug(f"Generated prompt: {prompt}")

        # Hugging Face API request
        headers = {
            "Authorization": f"Bearer {os.getenv('HF_API_KEY')}"
        }

        # Prepare payload
        data = {
            "inputs": prompt,
            "options": {"use_cache": False}  # Disable caching
        }

        # Make the request to Hugging Face Inference API
        #response = requests.post(
            #f"{HUGGINGFACE_API_URL}/{MODEL_NAMES[model_name]}",
            #headers=headers,
            #json=data
        #)

        response = requests.post(
            f"{os.getenv("GOOGLE_COLAB_URL")}",
            headers=headers,
            json=data
        )

        if response.status_code == 200:
            # Parse the response JSON
            response_json = response.json()
            generated_text = response_json[0]["generated_text"]
            logger.info(f"Received response from Hugging Face model: {generated_text}")

            # Tokenize the response into sentences
            sentences = sent_tokenize(generated_text)
            processed_response = "\n".join(sentences)
            logger.debug(f"Processed response: {processed_response}")

            # Return the response with CORS headers
            logger.info("Returning successful response with CORS headers.")
            return add_cors({
                "statusCode": 200,
                "body": json.dumps({
                    "response": processed_response,
                    "actual_response": generated_text,
                    "timestamp": timestamp  # Add timestamp to the response
                })
            })

        else:
            logger.error(f"Hugging Face API request failed with status code {response.status_code}")
            return add_cors({
                "statusCode": response.status_code,
                "body": json.dumps({"error": "Failed to generate response"})
            })

    except Exception as e:
        # Log the exception details
        logger.error(f"An error occurred: {str(e)}", exc_info=True)
        
        # Handle exceptions and return an error response
        return add_cors({
            "statusCode": 500,
            "body": json.dumps({"error": str(e)})
        })
