import json
import os
import boto3
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

# Get SageMaker endpoint name from environment variable
SAGEMAKER_ENDPOINT_NAME = os.environ.get("SAGEMAKER_ENDPOINT_NAME")
if not SAGEMAKER_ENDPOINT_NAME:
    raise ValueError("SAGEMAKER_ENDPOINT_NAME environment variable not set")

# Initialize SageMaker Runtime client
sagemaker_runtime = boto3.client("sagemaker-runtime")

# CORS headers
CORS_HEADERS = {
    "Content-Type": "application/json",
    "Access-Control-Allow-Origin": "*",
    "Access-Control-Allow-Methods": "GET, POST, OPTIONS",
    "Access-Control-Allow-Headers": "*",
    "Access-Control-Max-Age": "86400"
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

        # Parse API Gateway event (query parameters from GET request)
        query_params = event.get("queryStringParameters", {}) or {}
        urs_name = query_params.get("urs_name", "")
        section_name = query_params.get("section_name", "")
        k = int(query_params.get("k", 5))
        # Parse seen_indices from query parameter (comma-separated string or JSON)
        seen_indices_str = query_params.get("seen_indices", "")
        seen_indices = set(map(int, seen_indices_str.split(","))) if seen_indices_str else set()

        if not urs_name or not section_name:
            return {
                "statusCode": 400,
                "body": json.dumps({"error": "Missing urs_name or section_name"}),
                "headers": CORS_HEADERS
            }

        # Prepare payload for SageMaker endpoint
        payload = {
            "urs_name": urs_name,
            "section_name": section_name,
            "k": 50  # Search for 50 nearest neighbors to filter later
        }

        # Call SageMaker endpoint
        try:
            response = sagemaker_runtime.invoke_endpoint(
                EndpointName=SAGEMAKER_ENDPOINT_NAME,
                ContentType="application/json",
                Body=json.dumps(payload)
            )
            faiss_data = json.loads(response["Body"].read().decode("utf-8"))
            faiss_indices_all = faiss_data["indices"]  # List of 50 FAISS indices
        except sagemaker_runtime.exceptions.ClientError as e:
            if "ModelError" in str(e) and "FAISS index not found" in str(e):
                return {
                    "statusCode": 404,
                    "body": json.dumps({"error": f"No FAISS index found for urs_name: {urs_name}"}),
                    "headers": CORS_HEADERS
                }
            raise

        # Filter out previously seen indices and take first k
        faiss_indices = [idx for idx in faiss_indices_all if idx not in seen_indices][:k]
        if not faiss_indices:
            return {
                "statusCode": 200,
                "body": json.dumps({
                    "results": [],
                    "count": 0,
                    "faiss_indices": [],
                    "message": "No new distinct results available"
                }),
                "headers": CORS_HEADERS
            }

        # Connect to Neon PostgreSQL
        with psycopg2.connect(**DB_CONFIG) as conn:
            with conn.cursor() as cursor:
                query = """
                    SELECT cb.id, cb.batch_run_id, cb.urs_section_id, cb.block_number, cb.content_type, cb.content,
                           cb.coord_x1, cb.coord_y1, cb.coord_x2, cb.coord_y2, cb.created_at, cb.faiss_index_id,
                           sec.name AS section_name
                    FROM content_blocks cb
                    INNER JOIN urs_section_mapping usm ON cb.urs_section_id = usm.urs_section_id
                    INNER JOIN sections sec ON usm.section_id = sec.id
                    WHERE cb.faiss_index_id = ANY(%s)
                    AND sec.name = %s
                    ORDER BY cb.created_at DESC;
                """
                cursor.execute(query, (faiss_indices, section_name))
                results = cursor.fetchall()

        # Format response
        response_data = []
        retrieved_faiss_indices = []
        for row in results:
            response_data.append({
                "id": row[0],
                "batch_run_id": row[1],
                "urs_section_id": row[2],
                "block_number": row[3],
                "content_type": row[4],
                "content": row[5],
                "coordinates": {"x1": row[6], "y1": row[7], "x2": row[8], "y2": row[9]},
                "created_at": row[10].isoformat() if row[10] else None,
                "faiss_index_id": row[11],
                "section_name": row[12]
            })
            retrieved_faiss_indices.append(row[11])

        # Combine seen_indices with new retrieved indices for the client to store
        updated_seen_indices = list(seen_indices.union(retrieved_faiss_indices))

        return {
            "statusCode": 200,
            "body": json.dumps({
                "results": response_data,
                "count": len(response_data),
                "faiss_indices": retrieved_faiss_indices,
                "seen_indices": updated_seen_indices  # Return updated list for client
            }),
            "headers": CORS_HEADERS
        }

    except ValueError as e:
        return {
            "statusCode": 400,
            "body": json.dumps({"error": str(e)}),
            "headers": CORS_HEADERS
        }
    except sagemaker_runtime.exceptions.ClientError as e:
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