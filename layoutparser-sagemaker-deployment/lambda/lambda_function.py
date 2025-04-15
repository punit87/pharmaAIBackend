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
from datetime import datetime
import urllib.parse

# Configure logging
logger = logging.getLogger()
logger.setLevel(logging.INFO)

# AWS clients
s3_client = boto3.client("s3")
sagemaker_client = boto3.client("sagemaker-runtime")

# Configuration
S3_BUCKET = "aytanai-batch-processing"
ENDPOINT_NAME = os.getenv("SAGEMAKER_ENDPOINT_NAME", "<ENDPOINT_NAME>")
DB_CONFIG = {
    "dbname": "neondb",
    "user": "neondb_owner",
    "password": "npg_DU3Vxoi6cCIu",
    "host": "ep-shy-recipe-a406b4wg-pooler.us-east-1.aws.neon.tech",
    "port": "5432",
    "sslmode": "require"
}

# Load spaCy model
logger.info("Loading spaCy model 'en_core_web_lg'")
try:
    nlp = spacy.load("en_core_web_lg")
    logger.info("spaCy model loaded successfully")
except Exception as e:
    logger.error("Failed to load spaCy model: %s", str(e))
    raise

def preprocess_text(text):
    logger.debug("Preprocessing text: %s", text[:100])
    text = re.sub(r'(\d+)\s+([A-Z])', r'. \1 \2', text)
    text = ' '.join(text.split())
    logger.debug("Preprocessed text: %s", text[:100])
    return text

def clean_and_split_sentences(text):
    logger.debug("Cleaning and splitting sentences for text: %s", text[:100])
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
            logger.debug("Valid sentence added: %s", sentence)
            cleaned_sentences.append(sentence)
    logger.info("Cleaned sentences count: %d", len(cleaned_sentences))
    return cleaned_sentences

def setup_db_connection():
    logger.info("Setting up database connection")
    try:
        conn = psycopg2.connect(**DB_CONFIG)
        cursor = conn.cursor()
        logger.info("Database connection established")
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
        logger.info("Batch run created with batch_id: %s", batch_id)
        return conn, cursor, batch_id
    except Exception as e:
        logger.error("Failed to set up database connection: %s", str(e))
        raise

def preprocess_name_for_hash(name):
    logger.debug("Preprocessing name for hash: %s", name)
    name = re.sub(r'^\d+\s*', '', name).strip()
    processed_name = re.sub(r'[^a-z0-9]', '', name.lower())
    logger.debug("Processed name for hash: %s", processed_name)
    return processed_name

def lambda_handler(event, context):
    logger.info("Lambda handler invoked with event: %s", json.dumps(event, indent=2))
    
    # Parse S3 event
    for record in event["Records"]:
        s3_key = record["s3"]["object"]["key"]
        logger.info("Received S3 key: %s", s3_key)
        
        # Decode URL-encoded S3 key
        decoded_s3_key = urllib.parse.unquote(s3_key)
        logger.info("Decoded S3 key: %s", decoded_s3_key)
        
        if not decoded_s3_key.endswith(".docx"):
            logger.info("Skipping non-.docx file: %s", decoded_s3_key)
            continue

        # Download .docx file to /tmp (required for LibreOffice)
        tmp_docx = "/tmp/input.docx"
        logger.info("Downloading .docx file from S3: %s to %s", decoded_s3_key, tmp_docx)
        try:
            s3_client.download_file(S3_BUCKET, decoded_s3_key, tmp_docx)
            logger.info("Successfully downloaded .docx file")
        except Exception as e:
            logger.error("Failed to download .docx file: %s", str(e))
            raise

        # Download metadata.json
        tmp_metadata = "/tmp/metadata.json"
        logger.info("Downloading metadata.json from S3 to %s", tmp_metadata)
        try:
            s3_client.download_file(S3_BUCKET, "metadata/metadata.json", tmp_metadata)
            with open(tmp_metadata, "r") as f:
                metadata = json.load(f)
            logger.info("Metadata loaded: %s", json.dumps(metadata, indent=2))
        except Exception as e:
            logger.error("Failed to download or parse metadata.json: %s", str(e))
            raise

        doc_name = Path(decoded_s3_key).stem
        logger.debug("Document name: %s", doc_name)
        urs_name = next(
            (item["urs_name"] for item in metadata["documents"] if item["doc_name"] == f"{doc_name}.docx"),
            doc_name,
        )
        logger.info("URS name resolved: %s", urs_name)

        # Convert .docx to PDF and upload to S3
        pdf_s3_key = f"pdf/{doc_name}.pdf"
        logger.info("Converting .docx to PDF and uploading to S3: %s", pdf_s3_key)
        try:
            # Run LibreOffice, capturing output in /tmp
            subprocess.run(
                ["/opt/libreoffice25.2/program/soffice", "--headless", "--convert-to", "pdf", tmp_docx, "--outdir", "/tmp"],
                check=True,
            )
            # Read PDF and upload to S3
            tmp_pdf = "/tmp/input.pdf"
            with open(tmp_pdf, "rb") as f:
                pdf_data = f.read()
            s3_client.put_object(Bucket=S3_BUCKET, Key=pdf_s3_key, Body=pdf_data)
            logger.info("Successfully uploaded PDF to S3: %s", pdf_s3_key)
        except Exception as e:
            logger.error("Failed to convert .docx to PDF or upload to S3: %s", str(e))
            raise

        # Convert PDF to images using in-memory streaming
        logger.info("Converting PDF to images")
        try:
            images = convert_from_bytes(pdf_data, fmt="png")
            logger.info("PDF converted to %d images", len(images))
        except Exception as e:
            logger.error("Failed to convert PDF to images: %s", str(e))
            raise

        conn, cursor, batch_id = setup_db_connection()
        try:
            urs_hash = hashlib.md5(preprocess_name_for_hash(urs_name).encode()).hexdigest()
            logger.info("Generated URS hash: %s for urs_name: %s", urs_hash, urs_name)
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
                logger.info("Inserted new section with id: %s for section: %s", section_id, current_section)
            else:
                section_id = row[0]
                logger.info("Retrieved existing section id: %s for section: %s", section_id, current_section)

            cursor.execute(
                "INSERT INTO urs_section_mapping (urs_id, section_id) VALUES (%s, %s) ON CONFLICT DO NOTHING RETURNING urs_section_id",
                (urs_id, section_id),
            )
            row = cursor.fetchone()
            if row:
                urs_section_id = row[0]
                logger.info("Inserted new URS section mapping with urs_section_id: %s", urs_section_id)
            else:
                cursor.execute(
                    "SELECT urs_section_id FROM urs_section_mapping WHERE urs_id = %s AND section_id = %s",
                    (urs_id, section_id),
                )
                urs_section_id = cursor.fetchone()[0]
                logger.info("Retrieved existing urs_section_id: %s", urs_section_id)
            conn.commit()

            block_number = 1
            logger.info("Starting image processing loop with %d images", len(images))
            for idx, image in enumerate(images):
                logger.info("Processing image %d", idx)
                # Upload image to S3
                image_s3_key = f"images/{doc_name}_{idx}.png"
                logger.debug("Uploading image to S3: %s", image_s3_key)
                try:
                    img_byte_arr = BytesIO()
                    image.save(img_byte_arr, format="PNG")
                    img_byte_arr.seek(0)
                    s3_client.put_object(Bucket=S3_BUCKET, Key=image_s3_key, Body=img_byte_arr)
                    logger.debug("Uploaded image to S3: %s", image_s3_key)
                except Exception as e:
                    logger.error("Failed to upload image %d to S3: %s", idx, str(e))
                    raise

                # Create ZIP file in memory for SageMaker
                logger.debug("Creating in-memory ZIP for image %d", idx)
                try:
                    zip_buffer = BytesIO()
                    with zipfile.ZipFile(zip_buffer, "w", zipfile.ZIP_DEFLATED) as zipf:
                        img_byte_arr.seek(0)
                        zipf.writestr(f"image_{idx}.png", img_byte_arr.read())
                    zip_buffer.seek(0)
                    logger.debug("In-memory ZIP created for image %d", idx)
                except Exception as e:
                    logger.error("Failed to create in-memory ZIP for image %d: %s", idx, str(e))
                    raise

                # Call SageMaker endpoint
                logger.info("Invoking SageMaker endpoint: %s for image %d", ENDPOINT_NAME, idx)
                try:
                    response = sagemaker_client.invoke_endpoint(
                        EndpointName=ENDPOINT_NAME,
                        ContentType="application/zip",
                        Accept="application/json",
                        Body=zip_buffer.getvalue(),
                    )
                    layout_blocks = json.loads(response["Body"].read().decode())["layout_blocks"]
                    logger.info("SageMaker returned %d layout blocks for image %d", len(layout_blocks), idx)
                except Exception as e:
                    logger.error("SageMaker endpoint invocation failed for image %d: %s", idx, str(e))
                    raise

                # Process layout blocks
                image_np = np.array(image)
                image_cv = cv2.cvtColor(image_np, cv2.COLOR_RGB2BGR)
                logger.debug("Processing %d layout blocks for image %d", len(layout_blocks), idx)
                for block in sorted(layout_blocks, key=lambda x: x["coordinates"][1]):
                    block_type = block["type"]
                    x1, y1, x2, y2 = block["coordinates"]
                    logger.debug("Processing block type: %s at coordinates (%d, %d, %d, %d)", block_type, x1, y1, x2, y2)
                    try:
                        cropped = image_cv[y1:y2, x1:x2]
                        content = pytesseract.image_to_string(cropped, config="--psm 6 --oem 1").strip()
                        logger.debug("Extracted content: %s", content[:100])
                    except Exception as e:
                        logger.error("Failed to process OCR for block at (%d, %d, %d, %d): %s", x1, y1, x2, y2, str(e))
                        continue

                    if block_type == "title":
                        current_section = re.sub(r'^\d+\s*', '', content).strip()
                        section_hash = hashlib.md5(preprocess_name_for_hash(current_section).encode()).hexdigest()
                        logger.info("Detected title: %s with section hash: %s", current_section, section_hash)
                        cursor.execute("SELECT id FROM sections WHERE section_hash = %s", (section_hash,))
                        row = cursor.fetchone()
                        if not row:
                            cursor.execute(
                                "INSERT INTO sections (name, section_hash) VALUES (%s, %s) RETURNING id",
                                (current_section, section_hash),
                            )
                            section_id = cursor.fetchone()[0]
                            logger.info("Inserted new section with id: %s for title: %s", section_id, current_section)
                        else:
                            section_id = row[0]
                            logger.info("Retrieved existing section id: %s for title: %s", section_id, current_section)

                        cursor.execute(
                            "INSERT INTO urs_section_mapping (urs_id, section_id) VALUES (%s, %s) ON CONFLICT DO NOTHING RETURNING urs_section_id",
                            (urs_id, section_id),
                        )
                        row = cursor.fetchone()
                        if row:
                            urs_section_id = row[0]
                            logger.info("Inserted new URS section mapping with urs_section_id: %s", urs_section_id)
                        else:
                            cursor.execute(
                                "SELECT urs_section_id FROM urs_section_mapping WHERE urs_id = %s AND section_id = %s",
                                (urs_id, section_id),
                            )
                            urs_section_id = cursor.fetchone()[0]
                            logger.info("Retrieved existing urs_section_id: %s", urs_section_id)
                        conn.commit()
                        continue

                    content_lines = clean_and_split_sentences(content) if block_type in ["text", "list", "table"] else [content]
                    logger.debug("Content lines extracted: %d", len(content_lines))
                    for line in content_lines:
                        if line.strip():
                            logger.debug("Inserting content block: %s", line[:100])
                            cursor.execute(
                                """
                                INSERT INTO content_blocks (batch_run_id, urs_section_id, block_number, content_type, content,
                                                           coord_x1, coord_y1, coord_x2, coord_y2, created_at)
                                VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s)
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
                                ),
                            )
                            logger.info("Inserted content block number: %d", block_number)
                            block_number += 1
                    conn.commit()

            logger.info("Updating batch run to SUCCESS for batch_id: %s", batch_id)
            cursor.execute(
                "UPDATE batch_runs SET completed_at = %s, processed_files = %s, batch_status = %s WHERE id = %s",
                (datetime.utcnow().isoformat(), 1, "SUCCESS", batch_id),
            )
            conn.commit()

        except Exception as e:
            logger.error("Processing failed for batch_id: %s, error: %s", batch_id, str(e))
            cursor.execute(
                "UPDATE batch_runs SET completed_at = %s, processed_files = %s, batch_status = %s WHERE id = %s",
                (datetime.utcnow().isoformat(), 0, "FAILED", batch_id),
            )
            conn.commit()
            raise
        finally:
            logger.info("Closing database connection for batch_id: %s", batch_id)
            cursor.close()
            conn.close()

    logger.info("Lambda processing complete")
    return {
        "statusCode": 200,
        "body": json.dumps({"message": "Processing complete"}),
    }