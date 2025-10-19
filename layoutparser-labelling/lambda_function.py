import json
import logging
import boto3
import subprocess
from pathlib import Path
from pdf2image import convert_from_bytes
from io import BytesIO
import urllib.parse
import requests
import os

# Configure logging
logger = logging.getLogger()
logger.setLevel(logging.INFO)
logging.basicConfig(
    format='%(asctime)s - %(levelname)s - %(filename)s:%(lineno)d - %(message)s',
    datefmt='%Y-%m-%d %H:%M:%S'
)

# AWS clients
logger.info("Initializing AWS S3 client")
s3_client = boto3.client("s3")

# Configuration from environment variables
S3_BUCKET = os.environ.get("S3_BUCKET", "aytanai-batch-processing")
LABEL_STUDIO_URL = os.environ.get("LABEL_STUDIO_URL")
LABEL_STUDIO_API_KEY = os.environ.get("LABEL_STUDIO_API_KEY")

def create_label_studio_project(doc_name):
    """Create a new project in Label Studio."""
    headers = {
        "Authorization": f"Token {LABEL_STUDIO_API_KEY}",
        "Content-Type": "application/json"
    }
    # Limit doc_name to 33 characters to ensure title <= 50 characters
    max_doc_name_length = 33  # 50 - len("Doc Labeling - ")
    truncated_doc_name = doc_name[:max_doc_name_length]
    title = f"Doc Labeling - {truncated_doc_name}"
    
    project_data = {
        "title": title,
        "description": f"Labeling project for {doc_name}",
        "label_config": "<View><Image name=\"image\" value=\"$image\"/><RectangleLabels name=\"label\" toName=\"image\"><Label value=\"Title\" background=\"#FF0000\"/><Label value=\"Text\" background=\"#00FF00\"/><Label value=\"Table\" background=\"#0000FF\"/><Label value=\"List\" background=\"#FFFF00\"/><Label value=\"Figure\" background=\"#FF00FF\"/></RectangleLabels></View>"
    }
    try:
        logger.info("Creating project with doc_name: %s, title: %s", doc_name, title)
        logger.debug("Project data: %s", json.dumps(project_data, indent=2))
        response = requests.post(
            f"{LABEL_STUDIO_URL}/api/projects",
            headers=headers,
            json=project_data,
            timeout=10
        )
        response.raise_for_status()
        project_id = response.json()["id"]
        logger.info("Created Label Studio project with ID: %s", project_id)
        return project_id
    except requests.exceptions.HTTPError as e:
        logger.error("Failed to create Label Studio project: %s", str(e))
        logger.error("Response body: %s", response.text)
        raise
    except Exception as e:
        logger.error("Failed to create Label Studio project: %s", str(e))
        logger.error("Request URL: %s", f"{LABEL_STUDIO_URL}/api/projects")
        raise

def upload_tasks_to_label_studio(project_id, image_s3_keys, doc_name):
    """Upload tasks with S3 image URLs to Label Studio project."""
    headers = {
        "Authorization": f"Token {LABEL_STUDIO_API_KEY}",
        "Content-Type": "application/json"
    }
    # Use AWS_REGION from Lambda runtime environment
    aws_region = os.environ.get("AWS_REGION", "us-east-1")  # Fallback to us-east-1 if not set
    tasks = [
        {
            "data": {
                "image": f"https://{S3_BUCKET}.s3.{aws_region}.amazonaws.com/{urllib.parse.quote(image_s3_key)}",
                "document_name": doc_name
            }
        } for image_s3_key in image_s3_keys
    ]
    try:
        logger.debug("Uploading tasks: %s", json.dumps(tasks, indent=2))
        response = requests.post(
            f"{LABEL_STUDIO_URL}/api/projects/{project_id}/tasks/bulk",
            headers=headers,
            json=tasks
        )
        response.raise_for_status()
        logger.info("Successfully uploaded %d tasks to Label Studio", len(tasks))
    except requests.exceptions.HTTPError as e:
        logger.error("Failed to upload tasks to Label Studio: %s", str(e))
        logger.error("Response body: %s", response.text)
        raise
    except Exception as e:
        logger.error("Failed to upload tasks to Label Studio: %s", str(e))
        raise

def get_labeling_url(project_id):
    """Generate the URL for the labeling interface."""
    return f"{LABEL_STUDIO_URL}/projects/{project_id}/data"

def lambda_handler(event, context):
    logger.info("Lambda handler invoked with event: %s", json.dumps(event, indent=2))
    
    # Validate environment variables
    if not all([S3_BUCKET, LABEL_STUDIO_URL, LABEL_STUDIO_API_KEY]):
        logger.error("Missing required environment variables")
        raise ValueError("S3_BUCKET, LABEL_STUDIO_URL, and LABEL_STUDIO_API_KEY must be set")

    # Parse S3 event
    for record in event["Records"]:
        s3_key = record["s3"]["object"]["key"]
        logger.info("Processing S3 event for key: %s", s3_key)
        
        # Decode URL-encoded S3 key
        decoded_s3_key = urllib.parse.unquote(s3_key)
        logger.info("Decoded S3 key: %s", decoded_s3_key)
        
        if not decoded_s3_key.startswith("uploads/labeling/raw/") or not decoded_s3_key.endswith((".docx", ".pdf")):
            logger.info("Skipping invalid file: %s", decoded_s3_key)
            continue

        # Download document file to /tmp
        tmp_doc = "/tmp/input" + Path(decoded_s3_key).suffix
        logger.info("Downloading document from S3: %s to %s", decoded_s3_key, tmp_doc)
        try:
            s3_client.download_file(S3_BUCKET, decoded_s3_key, tmp_doc)
            logger.info("Successfully downloaded document file")
        except Exception as e:
            logger.error("Failed to download document: %s", str(e))
            raise

        # Generate PDF S3 key
        doc_name = Path(decoded_s3_key).stem
        pdf_s3_key = f"uploads/labeling/pdfs/{doc_name}.pdf"
        logger.info("Target PDF S3 key: %s", pdf_s3_key)

        # Convert document to PDF if not already PDF
        logger.info("Converting document to PDF")
        try:
            if decoded_s3_key.endswith(".pdf"):
                with open(tmp_doc, "rb") as f:
                    pdf_data = f.read()
                logger.debug("Document is already PDF")
            else:
                logger.debug("Converting DOCX to PDF using LibreOffice")
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
            logger.error("Failed to convert or upload PDF: %s", str(e))
            raise

        # Convert PDF to images
        logger.info("Converting PDF to images")
        try:
            images = convert_from_bytes(pdf_data, fmt="png")
            logger.info("Successfully converted PDF to %d images", len(images))
        except Exception as e:
            logger.error("Failed to convert PDF to images: %s", str(e))
            raise

        # Upload images to S3 and collect S3 keys
        image_s3_keys = []
        for idx, image in enumerate(images):
            image_s3_key = f"uploads/labeling/images/{doc_name}_{idx}.png"
            logger.info("Uploading image %d to S3: %s", idx, image_s3_key)
            try:
                img_byte_arr = BytesIO()
                image.save(img_byte_arr, format="PNG")
                img_byte_arr.seek(0)
                s3_client.put_object(Bucket=S3_BUCKET, Key=image_s3_key, Body=img_byte_arr)
                logger.info("Successfully uploaded image %d to S3", idx)
                image_s3_keys.append(image_s3_key)
            except Exception as e:
                logger.error("Failed to upload image %d: %s", idx, str(e))
                raise

        # Integrate with Label Studio
        logger.info("Integrating with Label Studio")
        try:
            # Create new project
            project_id = create_label_studio_project(doc_name)
            
            # Upload tasks with image S3 URLs
            upload_tasks_to_label_studio(project_id, image_s3_keys, doc_name)
            
            # Generate labeling URL
            labeling_url = get_labeling_url(project_id)
            logger.info("Labeling URL: %s", labeling_url)
            
            # Store labeling_url in S3 for frontend
            s3_client.put_object(
                Bucket=S3_BUCKET,
                Key=f"uploads/labeling/urls/{doc_name}.json",
                Body=json.dumps({"labeling_url": labeling_url})
            )
        except Exception as e:
            logger.error("Failed to integrate with Label Studio: %s", str(e))
            raise

    logger.info("Lambda processing completed successfully")
    return {
        "statusCode": 200,
        "body": json.dumps({
            "message": "Processing complete",
            "labeling_url": labeling_url
        })
    }