import json
import os
import bcrypt
import psycopg2
import hashlib
import uuid
import logging
import boto3
from dotenv import load_dotenv

# Set up logging
logging.basicConfig(level=logging.DEBUG, format='%(asctime)s - %(levelname)s - %(message)s')
logger = logging.getLogger()

# Initialize AWS KMS client
kms_client = boto3.client('kms')

# Helper function to create a standardized response
def create_response(status_code, message):
    """
    Create a JSON response with CORS headers.

    Args:
        status_code (int): HTTP status code for the response.
        message (str or dict): Response message, either as a string or dictionary.

    Returns:
        dict: Formatted response with CORS headers.
    """
    return {
        "statusCode": status_code,
        "body": json.dumps({"message": message} if isinstance(message, str) else message),
        "headers": {
            "Access-Control-Allow-Origin": "*",
            "Access-Control-Allow-Methods": "GET, POST, OPTIONS",
            "Access-Control-Allow-Headers": "Content-Type, Authorization"
        }
    }

# Signup handler
def lambda_handler(event, context):
    """Handles user signup and sends an activation email."""
    load_dotenv()
    conn, cursor = None, None
    try:
        data = json.loads(event['body'])
        name = data.get('name')
        email = data.get('email')
        password = data.get('password')
        reenter_password = data.get('reenter_password')

        # Validate input
        if not all([name, email, password, reenter_password]):
            return create_response(400, "All fields are required!")
        if password != reenter_password:
            return create_response(400, "Passwords do not match!")

        email = email.strip().lower()
        # Encrypt name and email using AWS KMS
        encrypted_name = encrypt_with_kms(name)
        encrypted_email = encrypt_with_kms(email)

        # Generate deterministic SHA-256 hash for email
        email_hash = hashlib.sha256(email.encode('utf-8')).hexdigest()

        # Generate masked email (first 2 alphabetic chars + mask rest, keep full domain)
        masked_email = mask_email(email)

        # Database connection
        conn = get_db_connection()
        cursor = conn.cursor()

        # Check if email_hash already exists (deterministic duplicate check)
        cursor.execute("SELECT * FROM users WHERE email_hash = %s", (email_hash,))
        if cursor.fetchone():
            return create_response(400, "Email already exists. Please use a different email.")

        # Generate activation token and hash password
        activation_token = generate_activation_token()
        hashed_password = hash_password(password)
        hashed_token = hashlib.sha256(activation_token.encode()).hexdigest()

        # Insert new user into database with encrypted name, encrypted email, email_hash, and masked_email
        cursor.execute("""
            INSERT INTO users (name, email, email_hash, masked_email, password, activation_token, active)
            VALUES (%s, %s, %s, %s, %s, %s, %s)
        """, (encrypted_name, encrypted_email, email_hash, masked_email, hashed_password, hashed_token, True))
        conn.commit()

        # Send activation email (uncomment if needed)
        # return send_activation_email(email, activation_token)
        return create_response(201, "Signup successful. Continue to Login")

    except Exception as e:
        logger.error(f"Error during signup: {str(e)}")
        return create_response(500, f"An internal server error occurred: {str(e)}")

    finally:
        if cursor:
            cursor.close()
        if conn:
            conn.close()


# Database connection
def get_db_connection():
    return psycopg2.connect(
        host=os.getenv("DB_HOST"),
        dbname=os.getenv("DB_NAME"),
        user=os.getenv("DB_USER"),
        password=os.getenv("DB_PASS")
    )

# KMS encryption function
def encrypt_with_kms(data):
    """
    Encrypt data using AWS KMS managed key.
    
    Args:
        data (str): Data to encrypt
    
    Returns:
        bytes: Encrypted data
    """
    try:
        response = kms_client.encrypt(
            KeyId='alias/key_neondb',  # Adjust if using a different alias or ARN
            Plaintext=data.encode('utf-8')
        )
        return response['CiphertextBlob']
    except Exception as e:
        logger.error(f"Failed to encrypt data with KMS: {str(e)}")
        raise

# Mask email function
def mask_email(email):
    """
    Mask the email, keeping only the first 2 alphabetic characters visible before the last @,
    and showing the full domain after the last @.
    
    Args:
        email (str): The email to mask
    
    Returns:
        str: Masked email (e.g., "jo****@example.com")
    """
    # Split on the last occurrence of @
    local_part, domain = email.rsplit('@', 1)
    
    # Extract first 2 alphabetic characters from local part
    alpha_chars = ''.join(c for c in local_part if c.isalpha())[:2]
    if not alpha_chars:
        alpha_chars = local_part[:2]  # Fallback to first 2 chars if no alphabets
    
    # Mask the rest of the local part
    masked_local = alpha_chars + '*' * (len(local_part) - len(alpha_chars))
    
    # Return with full domain unmasked
    return f"{masked_local}@{domain}"

# Email service
def send_activation_email(to_email, activation_token):
    ses_client = boto3.client('ses', region_name=os.getenv('AWS_REGION', 'us-east-2'))
    sender_email = os.getenv("EMAIL_USER")  # The verified sender email in SES
    subject = "Account Activation"
    activation_link = f"{os.getenv('BASE_URL')}/activate_account/{activation_token}"
    body_text = f"Activate your account by clicking the link: {activation_link}"

    try:
        # Send email using SES
        response = ses_client.send_email(
            Source=sender_email,
            Destination={
                'ToAddresses': [to_email]
            },
            Message={
                'Subject': {'Data': subject},
                'Body': {
                    'Text': {'Data': body_text}
                }
            }
        )
        logger.info(f"Activation email sent to {to_email}. Message ID: {response['MessageId']}")
        return create_response(201, "Signup successful. Check your email to activate your account. Please note it can take up to 30 minutes for the email to arrive")
    except Exception as e:
        logger.error(f"Failed to send email via SES: {e}")
        raise e

# Utility functions
def generate_activation_token():
    return str(uuid.uuid4())

def hash_password(password):
    return bcrypt.hashpw(password.encode(), bcrypt.gensalt()).decode()

def check_password(password, hashed):
    return bcrypt.checkpw(password.encode(), hashed.encode())