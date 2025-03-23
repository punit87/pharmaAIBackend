import json
import os
import logging
import psycopg2
import hashlib
import boto3
from dotenv import load_dotenv
from bcrypt import checkpw

# Set up logging
logging.basicConfig(level=logging.DEBUG, format='%(asctime)s - %(levelname)s - %(message)s')
logger = logging.getLogger()

# Initialize AWS KMS client
kms_client = boto3.client('kms')

# Helper function to create a standardized response
def create_response(status_code, message):
    return {
        "statusCode": status_code,
        "body": json.dumps({"message": message} if isinstance(message, str) else message),
        "headers": {
            "Access-Control-Allow-Origin": "*",
            "Access-Control-Allow-Methods": "GET, POST, OPTIONS",
            "Access-Control-Allow-Headers": "Content-Type, Authorization"
        }
    }

# Database connection
def get_db_connection():
    return psycopg2.connect(
        host=os.getenv("DB_HOST"),
        dbname=os.getenv("DB_NAME"),
        user=os.getenv("DB_USER"),
        password=os.getenv("DB_PASS")
    )

# Password verification
def check_password(password, hashed):
    return checkpw(password.encode(), hashed.encode())

# KMS decryption function
def decrypt_with_kms(ciphertext):
    """
    Decrypt data using AWS KMS managed key, handling memoryview from BYTEA.
    
    Args:
        ciphertext: Encrypted data (bytes or memoryview)
    
    Returns:
        str: Decrypted data, or None if decryption fails
    """
    if isinstance(ciphertext, memoryview):
        ciphertext = bytes(ciphertext)  # Convert memoryview to bytes
    if not isinstance(ciphertext, bytes) or not ciphertext:
        logger.error("Invalid ciphertext: must be non-empty bytes")
        return None
    try:
        logger.debug(f"Attempting to decrypt ciphertext of length {len(ciphertext)} bytes")
        response = kms_client.decrypt(CiphertextBlob=ciphertext)
        plaintext = response['Plaintext'].decode('utf-8')
        logger.debug(f"Decryption successful, key used: {response['KeyId']}")
        return plaintext
    except Exception as e:
        logger.error(f"Failed to decrypt data with KMS: {str(e)}")
        return None

def lambda_handler(event, context):
    """Handles user login with email and password."""
    load_dotenv()
    conn, cursor = None, None

    try:
        # Parse the request body
        data = json.loads(event.get('body', '{}'))
        email = data.get('email')
        password = data.get('password')

        # Validate input
        if not all([email, password]):
            return create_response(400, "Email and password are required!")

        # Normalize email and generate hash (since email is encrypted in DB)
        email = email.strip().lower()
        email_hash = hashlib.sha256(email.encode('utf-8')).hexdigest()

        # Database connection
        conn = get_db_connection()
        cursor = conn.cursor()

        # Check if the user exists using email_hash
        cursor.execute("""
            SELECT id, name, email, password, active, masked_email
            FROM users 
            WHERE email_hash = %s
        """, (email_hash,))
        user = cursor.fetchone()

        if not user:
            return create_response(404, "User not found.")

        user_id, encrypted_name, encrypted_email, hashed_password, is_active, masked_email = user

        # Check if the account is active
        if not is_active:
            return create_response(400, "Account is not activated. Please check your email.")

        # Verify password
        if not check_password(password, hashed_password):
            return create_response(401, "Invalid credentials.")

        # Decrypt name and email for the response (optional)
        # name = decrypt_with_kms(encrypted_name)
        #  if name is None:
            #  logger.warning(f"Decryption failed for name of user {user_id}. Using fallback.")
            #  name = "Unknown"


        logger.info(f"User {user_id} logged in successfully.")
        return create_response(200, {
            "message": "Login successful!",
            "user_id": user_id,
            # "name": name,
            "masked_email": masked_email
        })

    except Exception as e:
        logger.error(f"Error during login: {str(e)}")
        return create_response(500, f"An internal server error occurred: {str(e)}")

    finally:
        if cursor:
            cursor.close()
        if conn:
            conn.close()