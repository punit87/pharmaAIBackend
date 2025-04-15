#!/bin/bash

# S3 Bucket Setup and File Upload
# Handles:
#   - Clearing S3 bucket directories
#   - Uploading metadata.json
#   - Uploading SageMaker model folder
#   - Uploading .docx files for processing

# Exit on error
set -e

# Source environment variables if not already loaded
if [ -z "$AWS_REGION" ]; then
  SCRIPT_DIR="$( cd "$( dirname "${BASH_SOURCE[0]}" )" >/dev/null 2>&1 && pwd )"
  source "${SCRIPT_DIR}/config.sh"
fi

echo "==== S3 Operations ===="

# Clean up existing S3 directories
echo "Deleting objects in S3 prefixes..."
aws --profile ${S3_PROFILE} s3 rm s3://${S3_BUCKET}/uploads/ --recursive || echo "No objects to delete in uploads/"
aws --profile ${S3_PROFILE} s3 rm s3://${S3_BUCKET}/metadata/ --recursive || echo "No objects to delete in metadata/"
aws --profile ${S3_PROFILE} s3 rm s3://${S3_BUCKET}/images/ --recursive || echo "No objects to delete in images/"

# Upload metadata.json
echo "Uploading metadata.json to S3..."
aws --profile ${S3_PROFILE} s3 cp ${METADATA_FILE} s3://${S3_BUCKET}/metadata/metadata.json

# Upload SageMaker model folder
echo "Uploading SageMaker model folder to S3..."
aws --profile ${S3_PROFILE} s3 sync ${LOCAL_MODEL_DIR}/ s3://${S3_BUCKET}/${S3_SAGEMAKER_PREFIX}${SAGEMAKER_MODEL_NAME}/

# Upload .docx files for processing
echo "Uploading .docx files to S3..."
aws --profile ${S3_PROFILE} s3 sync ${LOCAL_UPLOADS_DIR}/ s3://${S3_BUCKET}/uploads/ --include "*.docx"

echo "S3 setup and file upload complete."
