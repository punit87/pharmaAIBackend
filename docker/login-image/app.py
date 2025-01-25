import json
import os
import logging
import psycopg2
from dotenv import load_dotenv
from bcrypt import checkpw

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

def check_password(password, hashed):
    return checkpw(password.encode(), hashed.encode())

def lambda_handler(event, context):
    """Handles user login."""
    load_dotenv()
    conn, cursor = None, None

    try:
        # Parse the request body
        data = json.loads(event.get('body', '{}'))
        email, password = data.get('email'), data.get('password')

        # Validate input
        if not all([email, password]):
            return create_response(400, "Email and password are required!")

        # Database connection
        conn = get_db_connection()
        cursor = conn.cursor()

        # Check if the user exists
        cursor.execute("SELECT id, email, password, active FROM users WHERE email = %s", (email,))
        user = cursor.fetchone()

        if not user:
            return create_response(404, "User not found.")

        user_id, user_email, hashed_password, is_active = user

        # Check if the account is active
        if not is_active:
            return create_response(400, "Account is not activated. Please check your email.")

        # Verify password
        if not check_password(password, hashed_password):
            return create_response(401, "Invalid credentials.")

        logger.info(f"User {user_id} logged in successfully.")
        return create_response(200, {"message": "Login successful!", "email": user_email})

    except Exception as e:
        logger.error(f"Error during login: {str(e)}")
        return create_response(500, f"An internal server error occurred: {str(e)}")

    finally:
        if cursor:
            cursor.close()
        if conn:
            conn.close()
