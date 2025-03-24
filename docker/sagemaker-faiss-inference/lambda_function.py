import json
import os
import requests
import psycopg2
from psycopg2.extras import execute_values

# Neon PostgreSQL config
DB_CONFIG = {
    "dbname": os.getenv("DB_NAME"),
    "user": os.getenv("DB_USER"),
    "password": os.getenv("DB_PASS"),
    "host": os.getenv("DB_HOST"),
    "port": os.getenv("DB_PORT"),
    "sslmode": "require"
}

# Get SageMaker endpoint URL from environment variable
SAGEMAKER_ENDPOINT = os.environ.get("SAGEMAKER_ENDPOINT")
if not SAGEMAKER_ENDPOINT:
    raise ValueError("SAGEMAKER_ENDPOINT environment variable not set")

# CORS headers
CORS_HEADERS = {
    "Content-Type": "application/json",
    "Access-Control-Allow-Origin": "*",  # Allows all origins
    "Access-Control-Allow-Methods": "GET, POST, OPTIONS",  # Allowed HTTP methods
    "Access-Control-Allow-Headers": "Content-Type",  # Allowed headers
    "Access-Control-Max-Age": "86400"  # Cache preflight response for 24 hours
}

def lambda_handler(event, context):
    try:
        # Handle CORS preflight OPTIONS request
        if event.get("httpMethod") == "OPTIONS":
            return {
                "statusCode": 200,
                "headers": CORS_HEADERS,
                "body": json.dumps({"message": "CORS preflight successful"})
            }

        # Parse API Gateway event
        query_params = event.get("queryStringParameters", {})
        urs_name = query_params.get("urs_name", "")
        section_name = query_params.get("section_name", "")
        k = int(query_params.get("k", 5))

        # Call SageMaker endpoint
        sagemaker_url = f"{SAGEMAKER_ENDPOINT}/query_faiss/?urs_name={urs_name}§ion_name={section_name}&k={k}"
        response = requests.get(sagemaker_url)
        response.raise_for_status()
        faiss_data = response.json()
        faiss_indices = faiss_data["indices"]

        # Connect to Neon PostgreSQL
        with psycopg2.connect(**DB_CONFIG) as conn:
            with conn.cursor() as cursor:
                query = """
                    SELECT cb.id, cb.source_file_run_id, cb.section_id, cb.block_number, cb.content_type, cb.content,
                          cb.coord_x1, cb.coord_y1, cb.coord_x2, cb.coord_y2, cb.created_at, cb.faiss_index_id
                    FROM content_blocks cb
                    WHERE cb.faiss_index_id = ANY(%s)
                    ORDER BY cb.created_at DESC;
                """
                cursor.execute(query, (faiss_indices,))
                results = cursor.fetchall()

        # Format response
        response = []
        for row in results:
            response.append({
                "id": row[0],
                "source_file_run_id": row[1],
                "section_id": row[2],
                "block_number": row[3],
                "content_type": row[4],
                "content": row[5],
                "coordinates": {"x1": row[6], "y1": row[7], "x2": row[8], "y2": row[9]},
                "created_at": row[10],
                "faiss_index_id": row[11]
            })

        return {
            "statusCode": 200,
            "body": json.dumps({"results": response, "count": len(response)}),
            "headers": CORS_HEADERS
        }

    except requests.exceptions.RequestException as e:
        return {
            "statusCode": 500,
            "body": json.dumps({"error": f"SageMaker error: {str(e)}"}),
            "headers": CORS_HEADERS
        }
    except psycopg2.Error as e:
        return {
            "statusCode": 500,
            "body": json.dumps({"error": f"Database error: {str(e)}"}),
            "headers": CORS_HEADERS
        }
    except Exception as e:
        return {
            "statusCode": 500,
            "body": json.dumps({"error": str(e)}),
            "headers": CORS_HEADERS
        }