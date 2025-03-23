import json
import os
import psycopg2
from psycopg2.extras import RealDictCursor

# Database configuration from environment variables
DB_CONFIG = {
    "dbname": os.getenv("DB_NAME"),
    "user": os.getenv("DB_USER"),
    "password": os.getenv("DB_PASS"),
    "host": os.getenv("DB_HOST"),
    "port": os.environ.get("DB_PORT", "5432"),
    "sslmode": "require"
}

# CORS headers to be included in every response
CORS_HEADERS = {
    "Content-Type": "application/json",
    "Access-Control-Allow-Origin": "*",  # Allow all origins; replace with specific origin if needed (e.g., "https://your-flutter-app.com")
    "Access-Control-Allow-Methods": "GET, OPTIONS",  # Allow GET and OPTIONS (for preflight)
    "Access-Control-Allow-Headers": "Content-Type",  # Allow Content-Type header
    "Access-Control-Max-Age": "86400"  # Cache preflight response for 24 hours
}

def get_db_connection():
    """Establish a connection to the PostgreSQL database."""
    return psycopg2.connect(**DB_CONFIG, cursor_factory=RealDictCursor)

def get_documents(filter=""):
    """Fetch unique document names with optional filter."""
    conn = get_db_connection()
    try:
        with conn.cursor() as cur:
            cur.execute("SELECT DISTINCT name FROM documents WHERE name ILIKE %s", (f"%{filter}%",))
            return cur.fetchall()
    except Exception as e:
        raise Exception(f"Error fetching documents: {str(e)}")
    finally:
        conn.close()

def get_source_files(document_names):
    """Fetch source files for given document names."""
    conn = get_db_connection()
    try:
        with conn.cursor() as cur:
            names = document_names.split(',')
            cur.execute("""
                SELECT sf.file_name
                FROM source_files sf
                JOIN documents d ON sf.document_id = d.id
                WHERE d.name = ANY(%s)
            """, (names,))
            return cur.fetchall()
    except Exception as e:
        raise Exception(f"Error fetching source files: {str(e)}")
    finally:
        conn.close()

def get_source_file_runs():
    """Fetch all source file runs with associated metadata and sections."""
    conn = get_db_connection()
    try:
        with conn.cursor() as cur:
            cur.execute("""
                SELECT sfr.id, d.name, sf.file_name as src_file, sfr.author, sfr.created_dt::text, 
                       sfr.last_modified_dt::text, sfr.number_pages, 
                       ARRAY_AGG(s.section_name) as sections
                FROM source_file_runs sfr
                JOIN source_files sf ON sfr.source_file_id = sf.id
                JOIN documents d ON sf.document_id = d.id
                LEFT JOIN source_file_run_sections srs ON sfr.id = srs.source_file_run_id
                LEFT JOIN sections s ON srs.section_id = s.id
                GROUP BY sfr.id, d.name, sf.file_name, sfr.author, sfr.created_dt, sfr.last_modified_dt, sfr.number_pages
            """)
            return cur.fetchall()
    except Exception as e:
        raise Exception(f"Error fetching source file runs: {str(e)}")
    finally:
        conn.close()

def get_sections(source_file_ids):
    """Fetch sections for given source file IDs."""
    conn = get_db_connection()
    try:
        with conn.cursor() as cur:
            ids = source_file_ids.split(',')
            cur.execute("""
                SELECT DISTINCT s.section_name
                FROM sections s
                JOIN source_file_run_sections srs ON s.id = srs.section_id
                WHERE srs.source_file_run_id = ANY(%s::int[])
            """, (ids,))
            return cur.fetchall()
    except Exception as e:
        raise Exception(f"Error fetching sections: {str(e)}")
    finally:
        conn.close()

def lambda_handler(event, context):
    """AWS Lambda handler function to process API requests with CORS support."""
    try:
        # Extract request details from the event
        http_method = event.get('httpMethod', '')
        path = event.get('path', '')
        query_params = event.get('queryStringParameters', {}) or {}

        # Handle OPTIONS request for CORS preflight
        if http_method == 'OPTIONS':
            return {
                'statusCode': 200,
                'body': json.dumps({'message': 'CORS preflight successful'}),
                'headers': CORS_HEADERS
            }

        # Only handle GET requests beyond this point
        if http_method != 'GET':
            return {
                'statusCode': 405,
                'body': json.dumps({'error': 'Method Not Allowed'}),
                'headers': CORS_HEADERS
            }

        # Route handling based on path
        if path == '/documents':
            filter = query_params.get('filter', '')
            result = get_documents(filter)
            return {
                'statusCode': 200,
                'body': json.dumps(result),
                'headers': CORS_HEADERS
            }

        elif path == '/source_files':
            document_names = query_params.get('document_names', '')
            if not document_names:
                return {
                    'statusCode': 400,
                    'body': json.dumps({'error': 'Missing document_names parameter'}),
                    'headers': CORS_HEADERS
                }
            result = get_source_files(document_names)
            return {
                'statusCode': 200,
                'body': json.dumps(result),
                'headers': CORS_HEADERS
            }

        elif path == '/source_file_runs':
            result = get_source_file_runs()
            return {
                'statusCode': 200,
                'body': json.dumps(result),
                'headers': CORS_HEADERS
            }

        elif path == '/sections':
            source_file_ids = query_params.get('source_file_ids', '')
            if not source_file_ids:
                return {
                    'statusCode': 400,
                    'body': json.dumps({'error': 'Missing source_file_ids parameter'}),
                    'headers': CORS_HEADERS
                }
            result = get_sections(source_file_ids)
            return {
                'statusCode': 200,
                'body': json.dumps(result),
                'headers': CORS_HEADERS
            }

        else:
            return {
                'statusCode': 404,
                'body': json.dumps({'error': 'Not Found'}),
                'headers': CORS_HEADERS
            }

    except Exception as e:
        return {
            'statusCode': 500,
            'body': json.dumps({'error': str(e)}),
            'headers': CORS_HEADERS
        }