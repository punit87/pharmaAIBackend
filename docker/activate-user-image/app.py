import json
import os
import hashlib
import logging
import psycopg2
from dotenv import load_dotenv

# Set up logging
logging.basicConfig(level=logging.DEBUG, format='%(asctime)s - %(levelname)s - %(message)s')
logger = logging.getLogger()

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

def lambda_handler(event, context):
    """Handles account activation."""
    load_dotenv()
    conn, cursor = None, None

    try:
        # Extract activation token from the path after the last "/"
        path = event.get('path', '')
        activation_token = path.split('/')[-1]

        if not activation_token:
            return create_response(400, "Activation token is required.")

        # Hash the token
        hashed_token = hashlib.sha256(activation_token.encode()).hexdigest()

        # Database connection
        conn = get_db_connection()
        cursor = conn.cursor()

        # Check if the token exists and is valid
        cursor.execute("SELECT id FROM users WHERE activation_token = %s", (hashed_token,))
        user = cursor.fetchone()

        if not user:
            return create_response(400, "Invalid or expired activation token.")

        user_id = user[0]

        # Activate the user account
        cursor.execute("UPDATE users SET active = TRUE, activation_token = NULL WHERE id = %s", (user_id,))
        conn.commit()

        logger.info(f"User {user_id} activated successfully.")
        return create_response(200, "Account successfully activated!")

    except Exception as e:
        logger.error(f"Error during account activation: {str(e)}")
        return create_response(500, f"An internal server error occurred: {str(e)}")

    finally:
        if cursor:
            cursor.close()
        if conn:
            conn.close()
