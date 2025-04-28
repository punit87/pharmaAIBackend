#!/bin/bash

# Exit on any error
set -e

# Source configuration variables
if [ ! -f config.sh ]; then
    echo "Error: config.sh not found"
    exit 1
fi
source config.sh

# Validate required environment variables
required_vars=(
    "AWS_REGION"
    "ECR_REPOSITORY"
    "LAMBDA_FUNCTION_NAME"
    "AWS_ACCOUNT_ID"
)
for var in "${required_vars[@]}"; do
    if [ -z "${!var}" ]; then
        echo "Error: $var is not set in config.sh"
        exit 1
    fi
done

# Set variables
IMAGE_TAG="latest"
ECR_REGISTRY="${AWS_ACCOUNT_ID}.dkr.ecr.${AWS_REGION}.amazonaws.com"
IMAGE_URI="${ECR_REGISTRY}/${ECR_REPOSITORY}:${IMAGE_TAG}"

# Login to ECR using aytanai-ecr-user
echo "Logging in to ECR with aytanai-ecr-user..."
aws ecr get-login-password --region "${AWS_REGION}" --profile aytanai-ecr-user | docker login --username AWS --password-stdin "${ECR_REGISTRY}"

# Create ECR repository if it doesn't exist using aytanai-ecr-user
echo "Checking if ECR repository exists with aytanai-ecr-user..."
aws ecr describe-repositories --region "${AWS_REGION}" --repository-names "${ECR_REPOSITORY}" --profile aytanai-ecr-user >/dev/null 2>&1 || \
    aws ecr create-repository --region "${AWS_REGION}" --repository-name "${ECR_REPOSITORY}" --profile aytanai-ecr-user

# Delete existing images in the repository
echo "Deleting existing images in ECR repository with aytanai-ecr-user..."
IMAGE_IDS=$(aws ecr list-images --region "${AWS_REGION}" --repository-name "${ECR_REPOSITORY}" --profile aytanai-ecr-user --query 'imageIds[*]' --output json | jq -r '.[] | "--image-ids imageTag=\(.imageTag)"' || echo "")
if [ -n "$IMAGE_IDS" ]; then
    aws ecr batch-delete-image --region "${AWS_REGION}" --repository-name "${ECR_REPOSITORY}" --profile aytanai-ecr-user $IMAGE_IDS || echo "No images to delete or deletion failed"
else
    echo "No images found in repository"
fi

# Clear Docker cache
echo "Clearing Docker cache..."
docker builder prune -f

# Build Docker image for linux/arm64
echo "Building Docker image for linux/arm64..."
export DOCKER_BUILDKIT=1 
docker buildx build --output type=docker --output=type=image,oci-mediatypes=false --provenance=false --platform linux/arm64 -t "${ECR_REPOSITORY}:${IMAGE_TAG}" .

# Tag Docker image
echo "Tagging Docker image..."
docker tag "${ECR_REPOSITORY}:${IMAGE_TAG}" "${IMAGE_URI}"

# Push Docker image to ECR with retries
echo "Pushing Docker image to ECR with aytanai-ecr-user..."
for i in {1..3}; do
    if docker push "${IMAGE_URI}"; then
        echo "Push succeeded"
        break
    else
        echo "Push attempt $i failed, retrying..."
        sleep 5
    fi
    if [ $i -eq 3 ]; then
        echo "Error: Failed to push image after 3 attempts"
        exit 1
    fi
done

# Verify image in ECR
echo "Verifying image in ECR..."
if ! aws ecr describe-images --region "${AWS_REGION}" --repository-name "${ECR_REPOSITORY}" --image-ids imageTag="${IMAGE_TAG}" --profile aytanai-ecr-user >/dev/null 2>&1; then
    echo "Error: Failed to verify image in ECR"
    exit 1
fi

# Check image architecture and log manifest
echo "Verifying image architecture..."
RAW_RESPONSE=$(aws ecr batch-get-image \
    --region "${AWS_REGION}" \
    --repository-name "${ECR_REPOSITORY}" \
    --image-ids imageTag="${IMAGE_TAG}" \
    --profile aytanai-ecr-user \
    --output json 2>/dev/null || echo "{}")
echo "Raw ECR response:"
echo "$RAW_RESPONSE" | jq .
MANIFEST=$(echo "$RAW_RESPONSE" | jq -r '.images[].imageManifest' 2>/dev/null || echo "")
if [ -z "$MANIFEST" ]; then
    echo "Error: No manifest found for image. Check permissions or push integrity."
    exit 1
fi

# Wait for any ongoing Lambda update to complete using aytanai-lambda-user
echo "Checking for ongoing Lambda updates with aytanai-lambda-user..."
aws lambda wait function-updated \
    --region "${AWS_REGION}" \
    --function-name "${LAMBDA_FUNCTION_NAME}" \
    --profile aytanai-lambda-user || echo "No ongoing updates or function does not exist"

# Update Lambda function using aytanai-lambda-user
echo "Updating Lambda function with aytanai-lambda-user..."
aws lambda update-function-code \
    --region "${AWS_REGION}" \
    --function-name "${LAMBDA_FUNCTION_NAME}" \
    --image-uri "${IMAGE_URI}" \
    --publish \
    --profile aytanai-lambda-user

# Wait for Lambda code update to complete using aytanai-lambda-user
echo "Waiting for Lambda code update to complete with aytanai-lambda-user..."
aws lambda wait function-updated \
    --region "${AWS_REGION}" \
    --function-name "${LAMBDA_FUNCTION_NAME}" \
    --profile aytanai-lambda-user

# Update Lambda function environment variables using aytanai-lambda-user
echo "Updating Lambda function environment variables with aytanai-lambda-user..."
aws lambda update-function-configuration \
    --region "${AWS_REGION}" \
    --function-name "${LAMBDA_FUNCTION_NAME}" \
    --role "${LAMBDA_ROLE_ARN}" \
    --environment "Variables={DB_NAME=${DB_NAME},DB_USER=${DB_USER},DB_PASS=${DB_PASS},DB_HOST=${DB_HOST},DB_PORT=${DB_PORT},SAGEMAKER_ENDPOINT_NAME=${SAGEMAKER_ENDPOINT_NAME}}" \
    --profile aytanai-lambda-user

# Wait for Lambda configuration update to complete using aytanai-lambda-user
echo "Waiting for Lambda configuration update to complete with aytanai-lambda-user..."
aws lambda wait function-updated \
    --region "${AWS_REGION}" \
    --function-name "${LAMBDA_FUNCTION_NAME}" \
    --profile aytanai-lambda-user

echo "Lambda function deployed successfully!"