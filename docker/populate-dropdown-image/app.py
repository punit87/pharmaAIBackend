import json
import psycopg2
import os
import re

# Database configuration from environment variables
DB_CONFIG = {
    "host": os.environ.get("DB_HOST", "localhost"),
    "port": os.environ.get("DB_PORT", "5432"),
    "dbname": os.environ.get("DB_NAME", "your_database"),
    "user": os.environ.get("DB_USER", "your_user"),
    "password": os.environ.get("DB_PASS", "your_password"),
    "sslmode":"require"
}

# CORS headers to include in all responses
CORS_HEADERS = {
    "Content-Type": "application/json",
    "Access-Control-Allow-Origin": "*",
    "Access-Control-Allow-Methods": "GET, OPTIONS",
    "Access-Control-Allow-Headers": "Content-Type, Authorization",
    "Access-Control-Max-Age": "86400"
}

# Helper function to get database connection
def get_db_connection():
    try:
        return psycopg2.connect(**DB_CONFIG)
    except Exception as e:
        return {"error": f"Database connection error: {str(e)}"}

# Method to get unique URS names for dropdown
def get_urs_list():
    conn = None
    try:
        conn = get_db_connection()
        if isinstance(conn, dict) and "error" in conn:
            return {
                "statusCode": 500,
                "headers": CORS_HEADERS,
                "body": json.dumps({"error": conn["error"]})
            }
        
        with conn.cursor() as cur:
            cur.execute("SELECT id, name FROM urs ORDER BY name")
            urs_list = [{"id": row[0], "name": row[1]} for row in cur.fetchall()]
        return {
            "statusCode": 200,
            "headers": CORS_HEADERS,
            "body": json.dumps(urs_list)
        }
    except Exception as e:
        return {
            "statusCode": 500,
            "headers": CORS_HEADERS,
            "body": json.dumps({"error": f"Error fetching URS list: {str(e)}"})
        }
    finally:
        if conn and not isinstance(conn, dict):
            conn.close()

# Method to get sections for a given urs_id that exist in content_blocks
def get_sections_by_urs(urs_id):
    conn = None
    try:
        conn = get_db_connection()
        if isinstance(conn, dict) and "error" in conn:
            return {
                "statusCode": 500,
                "headers": CORS_HEADERS,
                "body": json.dumps({"error": conn["error"]})
            }
        
        with conn.cursor() as cur:
            query = """
                SELECT DISTINCT s.id, s.name
                FROM sections s
                JOIN urs_section_mapping usm ON s.id = usm.section_id
                JOIN content_blocks cb ON usm.urs_section_id = cb.urs_section_id
                WHERE usm.urs_id = %s
                ORDER BY s.name
            """
            cur.execute(query, (urs_id,))
            sections = [{"id": row[0], "name": row[1]} for row in cur.fetchall()]
        return {
            "statusCode": 200,
            "headers": CORS_HEADERS,
            "body": json.dumps(sections)
        }
    except Exception as e:
        return {
            "statusCode": 500,
            "headers": CORS_HEADERS,
            "body": json.dumps({"error": f"Error fetching sections: {str(e)}"})
        }
    finally:
        if conn and not isinstance(conn, dict):
            conn.close()

# Lambda handler
def lambda_handler(event, context):
    try:
        # Extract path from API Gateway event
        path = event.get("path", "")
        
        # Handle OPTIONS request for CORS preflight
        if event.get("httpMethod") == "OPTIONS":
            return {
                "statusCode": 200,
                "headers": CORS_HEADERS,
                "body": json.dumps({})
            }
        
        # Route based on path
        if path.endswith("/urs"):
            return get_urs_list()
        elif re.match(r".*/sections/\d+$", path):
            # Extract urs_id from path (e.g., /dev/sections/123)
            urs_id = int(path.split("/")[-1])
            return get_sections_by_urs(urs_id)
        else:
            return {
                "statusCode": 404,
                "headers": CORS_HEADERS,
                "body": json.dumps({"error": "Invalid path"})
            }
    except Exception as e:
        return {
            "statusCode": 500,
            "headers": CORS_HEADERS,
            "body": json.dumps({"error": f"Handler error: {str(e)}"})
        }