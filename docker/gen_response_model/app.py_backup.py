import json
import os
import logging
from nltk.tokenize import sent_tokenize
from huggingface_hub import InferenceClient
from datetime import datetime

# Set up logging
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

# Ensure the NLTK data directory is set (for redundancy)
os.environ["NLTK_DATA"] = "/usr/share/nltk_data"

# Model names mapping
MODEL_NAMES = {
    "GPT-2": "openai-community/gpt2",
    "T5": "google-t5/t5-small",
    "GPT-Neo": "EleutherAI/gpt-neo-2.7B",
    "BART": "facebook/bart-large",
}

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
        timestamp = datetime.utcnow().isoformat()
        # Generate the prompt
        prompt = f'''
        You are an advanced assistant specializing in generating meaningful and context-aware content based on User Requirements Specifications (URS). 
        Using your extensive knowledge base, identify and analyze any relevant URS that corresponds to the following document: "{document_heading}". 
        Focus specifically on the section titled "{section_name}", and generate 4 bullet points that are clear, detailed, and highly relevant to this section.
        This request was generated at timestamp: {timestamp}. Please come up with a different response than the last time. Also the response should no tbe empty string.
        '''

        logger.debug(f"Generated prompt: {prompt}")
        
        # Initialize the Hugging Face Inference Client
        inference_client = InferenceClient(token=os.getenv("HF_API_KEY"))
        logger.info("Initialized Hugging Face Inference Client.")

        response = inference_client.text_generation(
            model=MODEL_NAMES[model_name],
            prompt=prompt,
            max_new_tokens=100,
            temperature=0.7,
            top_p=0.9
        )
        logger.info(f"Received response from Hugging Face model: {response}")

        # Tokenize the response into sentences
        sentences = sent_tokenize(response)
        processed_response = "\n".join(sentences)
        logger.debug(f"Processed response: {processed_response}")

        # Return the response with CORS headers
        logger.info("Returning successful response with CORS headers.")
             # Get the current timestamp
        timestamp = datetime.utcnow().isoformat()
        return add_cors({
            "statusCode": 200,
            "body": json.dumps({
                "response": processed_response,
                "actual_response": response,
                "timestamp": timestamp  # Add timestamp to the response
            })
        })

    except Exception as e:
        # Log the exception details
        logger.error(f"An error occurred: {str(e)}", exc_info=True)
        
        # Handle exceptions and return an error response
        return add_cors({
            "statusCode": 500,
            "body": json.dumps({"error": str(e)})
        })
