import json
import os
import boto3
import psycopg2
from psycopg2.extras import execute_values
import faiss
import numpy as np
import hashlib
import re
import tempfile
import logging
from datetime import datetime

# Configure logging
logger = logging.getLogger()
logger.setLevel(logging.INFO)

# Structured logging formatter
class StructuredFormatter(logging.Formatter):
    def format(self, record):
        log_entry = {
            "timestamp": datetime.utcnow().isoformat(),
            "level": record.levelname,
            "message": record.getMessage(),
            "function_name": record.funcName,
            "line_number": record.lineno
        }
        return json.dumps(log_entry)

handler = logging.StreamHandler()
handler.setFormatter(StructuredFormatter())
logger.addHandler(handler)

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
    logger.error("SAGEMAKER_ENDPOINT_NAME environment variable not set")
    raise ValueError("SAGEMAKER_ENDPOINT_NAME environment variable not set")

# Initialize SageMaker Runtime client
sagemaker_runtime = boto3.client("sagemaker-runtime")

# Initialize S3 client
s3_client = boto3.client("s3")

# S3 bucket and prefix for FAISS indexes
S3_BUCKET = "aytanai-batch-processing"
S3_FAISS_PREFIX = "faiss_indexes"

# CORS headers
CORS_HEADERS = {
    "Content-Type": "application/json",
    "Access-Control-Allow-Origin": "*",
    "Access-Control-Allow-Methods": "GET, POST, OPTIONS",
    "Access-Control-Allow-Headers": "*",
    "Access-Control-Max-Age": "86400"
}

def preprocess_name_for_hash(name):
    """Preprocess urs_name for hashing, consistent with final_layout_parser.ipynb."""
    logger.debug(f"Preprocessing name for hash: {name}")
    name = re.sub(r'^\d+\s*', '', name).strip()
    processed_name = re.sub(r'[^a-z0-9]', '', name.lower())
    logger.debug(f"Processed name: {processed_name}")
    return processed_name

def get_faiss_index_s3_key(urs_name):
    """Generate S3 key for FAISS index based on urs_name."""
    logger.debug(f"Generating S3 key for urs_name: {urs_name}")
    hashed_name = hashlib.md5(preprocess_name_for_hash(urs_name).encode()).hexdigest()
    s3_key = f"{S3_FAISS_PREFIX}/faiss_index.index"
    logger.debug(f"Generated S3 key: {s3_key}")
    return s3_key

def download_faiss_index_from_s3(urs_name):
    """Download FAISS index from S3 to a temporary file and return the file path."""
    #s3_key = get_faiss_index_s3_key(urs_name)
    s3_key = f"{S3_FAISS_PREFIX}/faiss_index.index"
    temp_file = os.path.join(tempfile.gettempdir(), f"faiss_index.index")
    logger.info(f"Attempting to download FAISS index from S3: bucket={S3_BUCKET}, key={s3_key}, temp_file={temp_file}")
    
    try:
        s3_client.download_file(S3_BUCKET, s3_key, temp_file)
        logger.info(f"Successfully downloaded FAISS index to {temp_file}")
        return temp_file
    except s3_client.exceptions.ClientError as e:
        if e.response['Error']['Code'] == '404':
            logger.warning(f"No FAISS index found in S3 for urs_name: {urs_name}, key: {s3_key}")
            return None
        logger.error(f"S3 download error: {str(e)}")
        raise

def lambda_handler(event, context):
    logger.info(f"Lambda invoked with event: {json.dumps(event)}")
    try:
        # Handle CORS preflight OPTIONS request
        if event.get("httpMethod") == "OPTIONS":
            logger.info("Handling CORS preflight OPTIONS request")
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
        seen_indices_str = query_params.get("seen_indices", "")
        seen_indices = set(map(int, seen_indices_str.split(","))) if seen_indices_str else set()
        logger.info(f"Parsed query parameters: urs_name={urs_name}, section_name={section_name}, k={k}, seen_indices={seen_indices}")

        # Validate required parameters
        if not urs_name or not section_name:
            logger.error("Missing urs_name or section_name in query parameters")
            return {
                "statusCode": 400,
                "body": json.dumps({"error": "Missing urs_name or section_name"}),
                "headers": CORS_HEADERS
            }

        # Prepare payload for SageMaker endpoint
        payload = {
            "urs_name": urs_name,
            "section_name": section_name
        }
        logger.debug(f"Prepared SageMaker payload: {payload}")

        # Call SageMaker endpoint to get query embedding
        try:
            logger.info(f"Invoking SageMaker endpoint: {SAGEMAKER_ENDPOINT_NAME}")
            start_time = datetime.utcnow()
            response = sagemaker_runtime.invoke_endpoint(
                EndpointName=SAGEMAKER_ENDPOINT_NAME,
                ContentType="application/json",
                Body=json.dumps(payload)
            )
            elapsed_time = (datetime.utcnow() - start_time).total_seconds()
            logger.info(f"SageMaker endpoint invoked successfully, took {elapsed_time:.2f} seconds")
            embedding_data = json.loads(response["Body"].read().decode("utf-8"))
            query_embedding = np.array(embedding_data["query_embedding"], dtype=np.float32)
            logger.debug("Successfully retrieved query embedding from SageMaker")
        except sagemaker_runtime.exceptions.ClientError as e:
            logger.error(f"SageMaker ClientError: {str(e)}")
            return {
                "statusCode": 500,
                "body": json.dumps({"error": f"SageMaker error: {str(e)}"}),
                "headers": CORS_HEADERS
            }

        # Download and load FAISS index from S3
        faiss_index_path = download_faiss_index_from_s3(urs_name)
        if not faiss_index_path:
            logger.warning(f"No FAISS index found for urs_name: {urs_name}")
            return {
                "statusCode": 404,
                "body": json.dumps({"error": f"No FAISS index found for urs_name: {urs_name}"}),
                "headers": CORS_HEADERS
            }
        logger.info(f"Loading FAISS index from {faiss_index_path}")
        faiss_index = faiss.read_index(faiss_index_path)

        # Perform FAISS search
        logger.info(f"Performing FAISS search for k=50 nearest neighbors")
        distances, indices = faiss_index.search(query_embedding, 50)
        faiss_indices_all = indices[0].tolist()
        logger.debug(f"FAISS search results: indices={faiss_indices_all}, distances={distances[0].tolist()}")

        # Filter out previously seen indices and take first k
        faiss_indices = [idx for idx in faiss_indices_all if idx not in seen_indices][:k]
        logger.info(f"Filtered FAISS indices (k={k}): {faiss_indices}")
        if not faiss_indices:
            logger.info("No new distinct results available after filtering seen indices")
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
        logger.info("Connecting to Neon PostgreSQL")
        start_time = datetime.utcnow()
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
                logger.debug(f"Executing SQL query with faiss_indices={faiss_indices}, section_name={section_name}")
                cursor.execute(query, (faiss_indices, section_name))
                results = cursor.fetchall()
                elapsed_time = (datetime.utcnow() - start_time).total_seconds()
                logger.info(f"Retrieved {len(results)} rows from database, took {elapsed_time:.2f} seconds")

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
        logger.debug(f"Formatted response data: {len(response_data)} items, retrieved_faiss_indices={retrieved_faiss_indices}")

        # Combine seen_indices with new retrieved indices for the client to store
        updated_seen_indices = list(seen_indices.union(retrieved_faiss_indices))
        logger.debug(f"Updated seen_indices: {updated_seen_indices}")

        # Clean up temporary FAISS index file
        if os.path.exists(faiss_index_path):
            logger.info(f"Cleaning up temporary FAISS index file: {faiss_index_path}")
            os.remove(faiss_index_path)

        logger.info(f"Returning successful response with {len(response_data)} results")
        return {
            "statusCode": 200,
            "body": json.dumps({
                "results": response_data,
                "count": len(response_data),
                "faiss_indices": retrieved_faiss_indices,
                "seen_indices": updated_seen_indices
            }),
            "headers": CORS_HEADERS
        }

    except ValueError as e:
        logger.error(f"ValueError: {str(e)}")
        return {
            "statusCode": 400,
            "body": json.dumps({"error": str(e)}),
            "headers": CORS_HEADERS
        }
    except sagemaker_runtime.exceptions.ClientError as e:
        logger.error(f"SageMaker ClientError: {str(e)}")
        return {
            "statusCode": 500,
            "body": json.dumps({"error": f"SageMaker error: {str(e)}"}),
            "headers": CORS_HEADERS
        }
    except psycopg2.Error as e:
        logger.error(f"Database error: {str(e)}")
        return {
            "statusCode": 500,
            "body": json.dumps({"error": f"Database error: {str(e)}"}),
            "headers": CORS_HEADERS
        }
    except Exception as e:
        logger.error(f"Unexpected error: {str(e)}", exc_info=True)
        return {
            "statusCode": 500,
            "body": json.dumps({"error": str(e)}),
            "headers": CORS_HEADERS
        }