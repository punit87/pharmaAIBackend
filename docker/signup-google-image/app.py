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
    return {
        "statusCode": status_code,
        "body": json.dumps({"message": message} if isinstance(message, str) else message),
        "headers": {
            "Access-Control-Allow-Origin": "*",
            "Access-Control-Allow-Methods": "GET, POST, OPTIONS",
            "Access-Control-Allow-Headers": "Content-Type, Authorization"
        }
    }

def lambda_handler(event, context):
    """Handles signup with Google credentials."""
    load_dotenv()
    conn, cursor = None, None
    try:
        data = json.loads(event['body'])
        name = data.get('name')
        email = data.get('email')

        # Validate input
        if not all([name, email]):
            return create_response(400, "All fields are required!")

        # Encrypt the username using AWS KMS
        encrypted_name = encrypt_with_kms(name)

        # Database connection
        conn = get_db_connection()
        cursor = conn.cursor()

        # Check if email already exists
        cursor.execute("SELECT * FROM users WHERE email = %s", (email,))
        if cursor.fetchone():
            return create_response(400, "Email already exists. Please use a different email.")

        # Generate random password and activation token
        password = generate_activation_code(12)
        activation_token = generate_activation_token()
        hashed_password = hash_password(password)
        hashed_token = hashlib.sha256(activation_token.encode()).hexdigest()

        # Insert new user into database with encrypted name
        cursor.execute("""
            INSERT INTO users (name, email, password, activation_token, active)
            VALUES (%s, %s, %s, %s, %s)
        """, (encrypted_name, email, hashed_password, hashed_token, True))
        conn.commit()

        return create_response(201, "Signup successful. Continue to Login")

    except Exception as e:
        logger.error(f"Error during signup with Google: {str(e)}")
        return create_response(500, f"An internal server error occurred: {str(e)}")

    finally:
        if cursor:
            cursor.close()
        if conn:
            conn.close()

# Database connection using environment variable
def get_db_connection():
    return psycopg2.connect(os.getenv("NEON_DB_CONNECTION_STRING"))

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
            KeyId='alias/aws/lambda',
            Plaintext=data.encode('utf-8')
        )
        return response['CiphertextBlob']
    except Exception as e:
        logger.error(f"Failed to encrypt data with KMS: {str(e)}")
        raise

# Email service (unchanged)
def send_activation_email(to_email, activation_token):
    ses_client = boto3.client('ses', region_name=os.getenv('AWS_REGION', 'us-east-2'))
    sender_email = os.getenv("EMAIL_USER")
    subject = "Account Activation"
    activate_user_api = os.getenv('ACTIVATE_USER_API')
    activation_link = f"{activate_user_api}/{activation_token}"
    body_text = f"Activate your account by clicking the link: {activation_link}"

    try:
        response = ses_client.send_email(
            Source=sender_email,
            Destination={'ToAddresses': [to_email]},
            Message={
                'Subject': {'Data': subject},
                'Body': {'Text': {'Data': body_text}}
            }
        )
        logger.info(f"Activation email sent to {to_email}. Message ID: {response['MessageId']}")
        return create_response(201, "Signup successful. Check your email to activate your account.")
    except Exception as e:
        logger.error(f"Failed to send email via SES: {e}")
        raise e

# Utility functions (unchanged)
def generate_activation_token():
    return str(uuid.uuid4())

def generate_activation_code(length=12):
    import random
    import string
    characters = string.ascii_letters + string.digits
    return ''.join(random.choice(characters) for _ in range(length))

def hash_password(password):
    return bcrypt.hashpw(password.encode(), bcrypt.gensalt()).decode()

def check_password(password, hashed):
    return bcrypt.checkpw(password.encode(), hashed.encode())