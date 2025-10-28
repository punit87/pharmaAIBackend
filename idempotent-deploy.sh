#!/bin/bash
# Idempotent deployment script that handles existing S3 bucket
set -e

echo "🚀 [DEPLOY] Starting idempotent CloudFormation deployment"

# Load environment variables from .env file
if [ -f .env ]; then
    export $(grep -v '^#' .env | xargs)
fi

# Configuration
STACK_NAME="${STACK_NAME:-pharma-rag-infrastructure-dev}"
BUCKET_NAME="pharma-documents-dev-864899869769-us-east-1-v5"
AWS_REGION="${AWS_REGION:-us-east-1}"
AWS_PROFILE="${AWS_PROFILE:-pharma}"

# Check if bucket exists
if aws s3 ls s3://${BUCKET_NAME} --profile ${AWS_PROFILE} --region ${AWS_REGION} 2>&1 | grep -q "NoSuchBucket"; then
    echo "✅ Bucket does not exist, will be created by CloudFormation"
    EXISTING_BUCKET=""
else
    echo "✅ Bucket already exists: ${BUCKET_NAME}"
    echo "⚠️  Using existing bucket instead of creating new one"
    EXISTING_BUCKET="${BUCKET_NAME}"
fi

# Run deployment
cd "/Users/bejoypramanick/iCloud Drive (Archive) - 1/Desktop/globistaan/projects/pharma/pharmaAIBackend"
./deploy.sh

echo "✅ Deployment complete"

