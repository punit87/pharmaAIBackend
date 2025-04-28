import json
import os
import subprocess
import boto3
import zipfile
from io import BytesIO
from pathlib import Path
from pdf2image import convert_from_bytes
import pytesseract
import cv2
import numpy as np
from PIL import Image
import psycopg2
import hashlib
import re
import spacy
import logging
import traceback
from datetime import datetime
import urllib.parse
from sentence_transformers import SentenceTransformer
import faiss
import tempfile

# Configure logging with detailed format
logger = logging.getLogger()
logger.setLevel(logging.INFO)
logging.basicConfig(
    format='%(asctime)s - %(levelname)s - %(filename)s:%(lineno)d - %(message)s',
    datefmt='%Y-%m-%d %H:%M:%S'
)

# AWS clients
logger.info("Initializing AWS clients")
s3_client = boto3.client("s3")
sagemaker_client = boto3.client("sagemaker-runtime")

# Configuration
S3_BUCKET = "aytanai-batch-processing"
FAISS_INDEX_PATH = "faiss_indexes/faiss_index.index"
ENDPOINT_NAME = os.getenv("SAGEMAKER_ENDPOINT_NAME", "<ENDPOINT_NAME>")
DB_CONFIG = {
    "dbname": os.getenv("DB_NAME", "neondb"),
    "user": os.getenv("DB_USER", "neondb_owner"),
    "password": os.getenv("DB_PASSWORD"),
    "host": os.getenv("DB_HOST", "ep-shy-recipe-a406b4wg-pooler.us-east-1.aws.neon.tech"),
    "port": os.getenv("DB_PORT", "5432"),
    "sslmode": os.getenv("DB_SSLMODE", "require")
}

# Load spaCy model
logger.info("Attempting to load spaCy model 'en_core_web_lg'")
try:
    nlp = spacy.load("en_core_web_lg")
    logger.info("Successfully loaded spaCy model")
except Exception as e:
    logger.error("Failed to load spaCy model: %s\n%s", str(e), traceback.format_exc())
    raise

# Initialize SentenceTransformer
logger.info("Attempting to load SentenceTransformer model")
try:
    sentence_transformer = SentenceTransformer('all-MiniLM-L6-v2')
    logger.info("Successfully loaded SentenceTransformer model")
except Exception as e:
    logger.error("Failed to load SentenceTransformer model: %s\n%s", str(e), traceback.format_exc())
    raise

def preprocess_text(text):
    logger.debug("Starting text preprocessing for text: %s", text[:100])
    try:
        text = re.sub(r'(\d+)\s+([A-Z])', r'. \1 \2', text)
        text = ' '.join(text.split())
        logger.debug("Preprocessed text result: %s", text[:100])
        return text
    except Exception as e:
        logger.error("Text preprocessing failed: %s\n%s", str(e), traceback.format_exc())
        raise

def clean_and_split_sentences(text):
    logger.debug("Starting clean and split sentences for text: %s", text[:100])
    try:
        preprocessed_text = preprocess_text(text)
        doc = nlp(preprocessed_text)
        cleaned_sentences = []
        special_chars = r'[|!@#$%^&*()_+=[\]{}:;"\'<>,/~`\\-]'

        for sent in doc.sents:
            sentence = sent.text.strip()
            logger.debug("Processing sentence: %s", sentence)
            sentence = sentence.replace('-', ' ')
            sentence = re.sub(f'^{special_chars}+', '', sentence.strip())
            sentence = re.sub(r'^\d+', '', sentence.strip())
            sentence = ' '.join(sentence.split())
            
            if not sentence:
                logger.debug("Skipping empty sentence")
                continue
                
            sentence = sentence.strip()
            if sentence[-1] not in '.!?':
                sentence += '.'
                
            tokens = nlp(sentence)
            has_verb = any(token.pos_ == "VERB" for token in tokens)
            is_long_enough = len(sentence) > 15
            
            if has_verb and is_long_enough:
                logger.debug("Adding valid sentence: %s", sentence)
                cleaned_sentences.append(sentence)
                
        logger.info("Completed sentence cleaning, total sentences: %d", len(cleaned_sentences))
        return cleaned_sentences
    except Exception as e:
        logger.error("Failed to clean and split sentences: %s\n%s", str(e), traceback.format_exc())
        raise

def setup_db_connection():
    logger.info("Initiating database connection setup")
    conn = None
    cursor = None
    try:
        conn = psycopg2.connect(**DB_CONFIG)
        conn.set_session(autocommit=False)  # Ensure explicit transaction control
        cursor = conn.cursor()
        logger.info("Database connection established successfully")
        
        logger.debug("Inserting new batch run record")
        cursor.execute(
            """
            INSERT INTO batch_runs (started_at, processed_files, batch_status)
            VALUES (%s, 0, 'RUNNING')
            RETURNING id
            """,
            (datetime.utcnow().isoformat(),),
        )
        batch_id = cursor.fetchone()[0]
        conn.commit()
        logger.info("Successfully created batch run with ID: %s", batch_id)
        return conn, cursor, batch_id
    except Exception as e:
        logger.error("Failed to set up database connection: %s\n%s", str(e), traceback.format_exc())
        if cursor:
            cursor.close()
        if conn:
            conn.rollback()
            conn.close()
        raise

def preprocess_name_for_hash(name):
    logger.debug("Preprocessing name for hash: %s", name)
    try:
        name = re.sub(r'^\d+\s*', '', name).strip()
        processed_name = re.sub(r'[^a-z0-9]', '', name.lower())
        logger.debug("Processed name for hash: %s", processed_name)
        return processed_name
    except Exception as e:
        logger.error("Failed to preprocess name for hash: %s\n%s", str(e), traceback.format_exc())
        raise

def extract_uuid_from_key(s3_key):
    logger.debug("Extracting UUID from S3 key: %s", s3_key)
    try:
        match = re.search(r'([0-9a-f]{8}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{12})_', s3_key)
        if match:
            uuid_str = match.group(1)
            logger.debug("Successfully extracted UUID: %s", uuid_str)
            return uuid_str
        logger.error("No UUID found in S3 key: %s", s3_key)
        raise ValueError("Invalid S3 key format: no UUID found")
    except Exception as e:
        logger.error("Failed to extract UUID: %s\n%s", str(e), traceback.format_exc())
        raise

def check_and_manage_faiss_index():
    logger.info("Checking FAISS index at s3://%s/%s", S3_BUCKET, FAISS_INDEX_PATH)
    try:
        # Check if FAISS index exists
        logger.debug("Performing head object check on FAISS index")
        s3_client.head_object(Bucket=S3_BUCKET, Key=FAISS_INDEX_PATH)
        logger.info("FAISS index exists, proceeding with backup")
        
        # Create backup with timestamp
        timestamp = datetime.utcnow().strftime("%d_%m_%Y_%H_%M_%S_%f")[:-3]
        backup_path = f"faiss_indexes/faiss_index_{timestamp}.index"
        logger.debug("Creating backup at: %s", backup_path)
        s3_client.copy_object(
            Bucket=S3_BUCKET,
            CopySource={'Bucket': S3_BUCKET, 'Key': FAISS_INDEX_PATH},
            Key=backup_path
        )
        logger.info("Successfully created FAISS index backup at s3://%s/%s", S3_BUCKET, backup_path)
        
        # Load existing index
        with tempfile.NamedTemporaryFile(suffix='.index') as tmp_file:
            logger.debug("Downloading FAISS index to temporary file")
            s3_client.download_file(S3_BUCKET, FAISS_INDEX_PATH, tmp_file.name)
            faiss_index = faiss.read_index(tmp_file.name)
            logger.info("Successfully loaded existing FAISS index with %d vectors", faiss_index.ntotal)
        return faiss_index, True
    except s3_client.exceptions.ClientError as e:
        if e.response['Error']['Code'] == '404':
            logger.info("FAISS index not found, creating new index")
            dimension = 384  # Dimension for all-MiniLM-L6-v2
            faiss_index = faiss.IndexFlatL2(dimension)
            logger.info("Created new FAISS index with dimension %d", dimension)
            return faiss_index, False
        else:
            logger.error("Error checking FAISS index: %s\n%s", str(e), traceback.format_exc())
            raise
    except Exception as e:
        logger.error("Unexpected error in check_and_manage_faiss_index: %s\n%s", str(e), traceback.format_exc())
        raise

def save_faiss_index(faiss_index):
    logger.info("Initiating FAISS index save to s3://%s/%s", S3_BUCKET, FAISS_INDEX_PATH)
    try:
        with tempfile.NamedTemporaryFile(suffix='.index') as tmp_file:
            logger.debug("Writing FAISS index to temporary file")
            faiss.write_index(faiss_index, tmp_file.name)
            logger.debug("Uploading FAISS index to S3")
            s3_client.upload_file(tmp_file.name, S3_BUCKET, FAISS_INDEX_PATH)
            logger.info("Successfully saved FAISS index with %d vectors", faiss_index.ntotal)
    except Exception as e:
        logger.error("Failed to save FAISS index: %s\n%s", str(e), traceback.format_exc())
        raise

def lambda_handler(event, context):
    logger.info("Lambda handler invoked with event: %s", json.dumps(event, indent=2))
    
    # Initialize or load FAISS index
    logger.info("Initializing FAISS index")
    try:
        faiss_index, is_existing_index = check_and_manage_faiss_index()
        current_index_count = faiss_index.ntotal if is_existing_index else 0
        logger.info("FAISS index initialized, current vector count: %d", current_index_count)
    except Exception as e:
        logger.error("Failed to initialize FAISS index: %s\n%s", str(e), traceback.format_exc())
        raise

    # Parse S3 event
    for record in event["Records"]:
        s3_key = record["s3"]["object"]["key"]
        logger.info("Processing S3 event for key: %s", s3_key)
        
        # Decode URL-encoded S3 key
        decoded_s3_key = urllib.parse.unquote(s3_key)
        logger.info("Decoded S3 key: %s", decoded_s3_key)
        
        if not decoded_s3_key.endswith((".docx", ".doc", ".pdf")):
            logger.info("Skipping non-document file: %s", decoded_s3_key)
            continue

        # Download document file to /tmp
        tmp_doc = "/tmp/input" + Path(decoded_s3_key).suffix
        logger.info("Downloading document from S3: %s to %s", decoded_s3_key, tmp_doc)
        try:
            s3_client.download_file(S3_BUCKET, decoded_s3_key, tmp_doc)
            logger.info("Successfully downloaded document file")
        except Exception as e:
            logger.error("Failed to download document: %s\n%s", str(e), traceback.format_exc())
            raise

        # Extract UUID from S3 key
        try:
            batch_uuid = extract_uuid_from_key(decoded_s3_key)
            logger.info("Extracted batch UUID: %s", batch_uuid)
        except Exception as e:
            logger.error("Failed to extract UUID: %s\n%s", str(e), traceback.format_exc())
            raise

        # Download metadata.json using the UUID
        metadata_s3_key = f"metadata/metadata_{batch_uuid}.json"
        tmp_metadata = "/tmp/metadata.json"
        logger.info("Downloading metadata from S3: %s to %s", metadata_s3_key, tmp_metadata)
        try:
            s3_client.download_file(S3_BUCKET, metadata_s3_key, tmp_metadata)
            with open(tmp_metadata, "r") as f:
                metadata = json.load(f)
            logger.info("Successfully loaded metadata: %s", json.dumps(metadata, indent=2))
        except Exception as e:
            logger.error("Failed to download or parse metadata: %s\n%s", str(e), traceback.format_exc())
            raise

        # Process document names
        doc_name = Path(decoded_s3_key).stem
        original_doc_name = doc_name[len(batch_uuid) + 1:] if batch_uuid in doc_name else doc_name
        decoded_doc_name = urllib.parse.unquote(original_doc_name)
        logger.info("Document names - doc_name: %s, decoded_s3_key: %s, batch_uuid: %s, original_doc_name: %s, decoded_doc_name: %s",
                   doc_name, decoded_s3_key, batch_uuid, original_doc_name, decoded_doc_name)
        
        urs_name = decoded_doc_name
        for item in metadata["documents"]:
            if item["doc_name"] == f"{decoded_doc_name}{Path(decoded_s3_key).suffix}":
                logger.info("Found matching document in metadata")
                urs_name = item["urs_name"]
                break
        logger.info("Resolved URS name: %s", urs_name)
        
        # Convert document to PDF if not already PDF
        pdf_s3_key = f"pdf/{doc_name}.pdf"
        logger.info("Converting document to PDF, target S3 key: %s", pdf_s3_key)
        try:
            if decoded_s3_key.endswith(".pdf"):
                with open(tmp_doc, "rb") as f:
                    pdf_data = f.read()
                logger.debug("Document is already PDF")
            else:
                logger.debug("Converting document to PDF using LibreOffice")
                subprocess.run(
                    ["/opt/libreoffice25.2/program/soffice", "--headless", "--convert-to", "pdf", tmp_doc, "--outdir", "/tmp"],
                    check=True,
                )
                tmp_pdf = "/tmp/input.pdf"
                with open(tmp_pdf, "rb") as f:
                    pdf_data = f.read()
                logger.debug("Document converted to PDF")
            s3_client.put_object(Bucket=S3_BUCKET, Key=pdf_s3_key, Body=pdf_data)
            logger.info("Successfully uploaded PDF to S3: %s", pdf_s3_key)
        except Exception as e:
            logger.error("Failed to convert or upload PDF: %s\n%s", str(e), traceback.format_exc())
            raise

        # Convert PDF to images
        logger.info("Converting PDF to images")
        try:
            images = convert_from_bytes(pdf_data, fmt="png")
            logger.info("Successfully converted PDF to %d images", len(images))
        except Exception as e:
            logger.error("Failed to convert PDF to images: %s\n%s", str(e), traceback.format_exc())
            raise

        # Setup database connection
        conn, cursor, batch_id = setup_db_connection()
        try:
            # Process URS
            logger.info("Processing URS for name: %s", urs_name)
            urs_hash = hashlib.md5(preprocess_name_for_hash(urs_name).encode()).hexdigest()
            logger.info("Generated URS hash: %s", urs_hash)
            
            cursor.execute(
                "INSERT INTO urs (name, urs_hash) VALUES (%s, %s) ON CONFLICT (name) DO NOTHING RETURNING id",
                (urs_name, urs_hash),
            )
            row = cursor.fetchone()
            if row:
                urs_id = row[0]
                logger.info("Inserted new URS with id: %s", urs_id)
            else:
                cursor.execute("SELECT id FROM urs WHERE name = %s", (urs_name,))
                urs_id = cursor.fetchone()[0]
                logger.info("Retrieved existing URS id: %s", urs_id)
            conn.commit()

            # Process initial section
            current_section = "notitle"
            section_hash = hashlib.md5(preprocess_name_for_hash(current_section).encode()).hexdigest()
            logger.debug("Generated section hash: %s for section: %s", section_hash, current_section)
            
            cursor.execute("SELECT id FROM sections WHERE section_hash = %s", (section_hash,))
            row = cursor.fetchone()
            if not row:
                cursor.execute(
                    "INSERT INTO sections (name, section_hash) VALUES (%s, %s) RETURNING id",
                    (current_section, section_hash),
                )
                section_id = cursor.fetchone()[0]
                logger.info("Inserted new section with id: %s", section_id)
            else:
                section_id = row[0]
                logger.info("Retrieved existing section id: %s", section_id)

            cursor.execute(
                "INSERT INTO urs_section_mapping (urs_id, section_id) VALUES (%s, %s) ON CONFLICT DO NOTHING RETURNING urs_section_id",
                (urs_id, section_id),
            )
            row = cursor.fetchone()
            if row:
                urs_section_id = row[0]
                logger.info("Inserted new URS section mapping with id: %s", urs_section_id)
            else:
                cursor.execute(
                    "SELECT urs_section_id FROM urs_section_mapping WHERE urs_id = %s AND section_id = %s",
                    (urs_id, section_id),
                )
                urs_section_id = cursor.fetchone()[0]
                logger.info("Retrieved existing URS section mapping id: %s", urs_section_id)
            conn.commit()

            block_number = 1
            logger.info("Starting image processing loop for %d images", len(images))
            for idx, image in enumerate(images):
                logger.info("Processing image %d of %d", idx + 1, len(images))
                
                # Upload image to S3
                image_s3_key = f"images/{doc_name}_{idx}.png"
                logger.debug("Uploading image to S3: %s", image_s3_key)
                try:
                    img_byte_arr = BytesIO()
                    image.save(img_byte_arr, format="PNG")
                    img_byte_arr.seek(0)
                    s3_client.put_object(Bucket=S3_BUCKET, Key=image_s3_key, Body=img_byte_arr)
                    logger.debug("Successfully uploaded image to S3")
                except Exception as e:
                    logger.error("Failed to upload image %d: %s\n%s", idx, str(e), traceback.format_exc())
                    raise

                # Create ZIP for SageMaker
                logger.debug("Creating in-memory ZIP for image %d", idx)
                try:
                    zip_buffer = BytesIO()
                    with zipfile.ZipFile(zip_buffer, "w", zipfile.ZIP_DEFLATED) as zipf:
                        img_byte_arr.seek(0)
                        zipf.writestr(f"image_{idx}.png", img_byte_arr.read())
                    zip_buffer.seek(0)
                    logger.debug("Successfully created in-memory ZIP")
                except Exception as e:
                    logger.error("Failed to create ZIP for image %d: %s\n%s", idx, str(e), traceback.format_exc())
                    raise

                # Call SageMaker endpoint
                logger.info("Invoking SageMaker endpoint %s for image %d", ENDPOINT_NAME, idx)
                try:
                    response = sagemaker_client.invoke_endpoint(
                        EndpointName=ENDPOINT_NAME,
                        ContentType="application/zip",
                        Accept="application/json",
                        Body=zip_buffer.getvalue(),
                    )
                    layout_blocks = json.loads(response["Body"].read().decode())["layout_blocks"]
                    logger.info("SageMaker returned %d layout blocks", len(layout_blocks))
                except Exception as e:
                    logger.error("SageMaker invocation failed for image %d: %s\n%s", idx, str(e), traceback.format_exc())
                    raise

                # Process layout blocks
                image_np = np.array(image)
                image_cv = cv2.cvtColor(image_np, cv2.COLOR_RGB2BGR)
                logger.debug("Processing %d layout blocks", len(layout_blocks))
                
                for block in sorted(layout_blocks, key=lambda x: x["coordinates"][1]):
                    block_type = block["type"]
                    x1, y1, x2, y2 = block["coordinates"]
                    logger.debug("Processing block type: %s at coordinates (%d, %d, %d, %d)", block_type, x1, y1, x2, y2)
                    
                    try:
                        cropped = image_cv[y1:y2, x1:x2]
                        content = pytesseract.image_to_string(cropped, config="--psm 6 --oem 1").strip()
                        logger.debug("OCR extracted content: %s", content[:100])
                    except Exception as e:
                        logger.error("OCR failed for block at (%d, %d, %d, %d): %s\n%s", x1, y1, x2, y2, str(e), traceback.format_exc())
                        continue

                    if block_type == "title":
                        current_section = re.sub(r'^\d+\s*', '', content).strip()[:255]
                        section_hash = hashlib.md5(preprocess_name_for_hash(current_section).encode()).hexdigest()
                        logger.info("Detected title: %s with hash: %s", current_section, section_hash)
                        
                        cursor.execute("SELECT id FROM sections WHERE section_hash = %s", (section_hash,))
                        row = cursor.fetchone()
                        if not row:
                            cursor.execute(
                                "INSERT INTO sections (name, section_hash) VALUES (%s, %s) RETURNING id",
                                (current_section, section_hash),
                            )
                            section_id = cursor.fetchone()[0]
                            logger.info("Inserted new section with id: %s", section_id)
                        else:
                            section_id = row[0]
                            logger.info("Retrieved existing section id: %s", section_id)

                        cursor.execute(
                            "INSERT INTO urs_section_mapping (urs_id, section_id) VALUES (%s, %s) ON CONFLICT DO NOTHING RETURNING urs_section_id",
                            (urs_id, section_id),
                        )
                        row = cursor.fetchone()
                        if row:
                            urs_section_id = row[0]
                            logger.info("Inserted new URS section mapping with id: %s", urs_section_id)
                        else:
                            cursor.execute(
                                "SELECT urs_section_id FROM urs_section_mapping WHERE urs_id = %s AND section_id = %s",
                                (urs_id, section_id),
                            )
                            urs_section_id = cursor.fetchone()[0]
                            logger.info("Retrieved existing URS section mapping id: %s", urs_section_id)
                        conn.commit()
                        continue

                    content_lines = clean_and_split_sentences(content) if block_type in ["text", "list", "table"] else [content]
                    logger.debug("Extracted %d content lines", len(content_lines))
                    
                    for line in content_lines:
                        if line.strip():
                            logger.debug("Processing content line: %s", line[:100])
                            try:
                                embedding = sentence_transformer.encode([line.strip()])
                                faiss_index.add(embedding)
                                faiss_index_id = current_index_count
                                current_index_count += 1
                                
                                logger.debug("Inserting content block with faiss_index_id: %d", faiss_index_id)
                                cursor.execute(
                                    """
                                    INSERT INTO content_blocks (
                                        batch_run_id, urs_section_id, block_number, content_type, content,
                                        coord_x1, coord_y1, coord_x2, coord_y2, created_at, faiss_index_id
                                    ) VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s)
                                    """,
                                    (
                                        batch_id,
                                        urs_section_id,
                                        block_number,
                                        block_type,
                                        line.strip(),
                                        x1,
                                        y1,
                                        x2,
                                        y2,
                                        datetime.utcnow().isoformat(),
                                        faiss_index_id,
                                    ),
                                )
                                logger.info("Inserted content block %d with faiss_index_id: %d", block_number, faiss_index_id)
                                block_number += 1
                            except Exception as e:
                                logger.error("Failed to process content line: %s\n%s", str(e), traceback.format_exc())
                                raise
                    conn.commit()

            # Save FAISS index
            logger.info("Saving updated FAISS index")
            save_faiss_index(faiss_index)

            # Update batch run status
            logger.info("Updating batch run status to SUCCESS for batch_id: %s", batch_id)
            cursor.execute(
                "UPDATE batch_runs SET completed_at = %s, processed_files = %s, batch_status = %s WHERE id = %s",
                (datetime.utcnow().isoformat(), 1, "SUCCESS", batch_id),
            )
            conn.commit()

        except Exception as e:
            logger.error("Processing failed for batch_id: %s: %s\n%s", batch_id, str(e), traceback.format_exc())
            if conn:
                logger.info("Rolling back database transaction")
                conn.rollback()
                cursor.execute(
                    "UPDATE batch_runs SET completed_at = %s, processed_files = %s, batch_status = %s WHERE id = %s",
                    (datetime.utcnow().isoformat(), 0, "FAILED", batch_id),
                )
                conn.commit()
            raise
        finally:
            logger.info("Cleaning up database connection for batch_id: %s", batch_id)
            if cursor:
                cursor.close()
            if conn:
                conn.close()

    logger.info("Lambda processing completed successfully")
    return {
        "statusCode": 200,
        "body": json.dumps({"message": "Processing complete"}),
    }