import json
import os
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
    """Handles Google Sign-In."""
    load_dotenv()
    conn, cursor = None, None

    try:
        # Parse the request body
        data = json.loads(event.get('body', '{}'))
        google_email = data.get('google_email')

        # Validate input
        if not google_email:
            return create_response(400, "Google email is required!")

        # Database connection
        conn = get_db_connection()
        cursor = conn.cursor()

        # Check if the Google user exists
        cursor.execute("SELECT id, name, email, active FROM users WHERE email = %s", (google_email,))
        user = cursor.fetchone()

        if user:
            user_id, name, email, is_active = user

            # Check if the account is active
            if not is_active:
                return create_response(400, "Account is not activated. Please check your email.")

            logger.info(f"Google user {user_id} found: {email}")
            return create_response(200, {"message": "Google email exists.", "name": name, "email": email})

        logger.info(f"Google email {google_email} not found.")
        return create_response(404, "Google email not found.")

    except Exception as e:
        logger.error(f"Error checking Google email: {str(e)}")
        return create_response(500, f"An internal server error occurred: {str(e)}")

    finally:
        if cursor:
            cursor.close()
        if conn:
            conn.close()
