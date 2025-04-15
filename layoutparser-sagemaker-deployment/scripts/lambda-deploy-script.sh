#!/bin/bash

# Lambda Function Deployment and S3 Trigger Setup
# Handles:
#   - Building and pushing Docker image to ECR
#   - Creating or updating Lambda function
#   - Setting up S3 trigger for Lambda function

# Exit on error
set -e

# Source environment variables if not already loaded
if [ -z "$AWS_REGION" ]; then
  SCRIPT_DIR="$( cd "$( dirname "${BASH_SOURCE[0]}" )" >/dev/null 2>&1 && pwd )"
  source "${SCRIPT_DIR}/config.sh"
fi

# --- Helper Functions ---
# Check if a Lambda function exists
check_lambda_exists() {
    aws --profile ${LAMBDA_PROFILE} lambda get-function --function-name "${LAMBDA_FUNCTION_NAME}" > /dev/null 2>&1
    return $?
}

echo "==== Lambda Deployment and S3 Trigger Setup ===="

# Step 1: Build and push Docker image
echo "Building and pushing Lambda Docker image..."

export DOCKER_BUILDKIT=1

# Authenticate to Amazon ECR
aws --profile ${ECR_PROFILE} ecr get-login-password --region "${AWS_REGION}" | docker login --username AWS --password-stdin ${AWS_ACCOUNT_ID}.dkr.ecr.${AWS_REGION}.amazonaws.com

# Check if ECR repository exists and handle image management
if aws --profile ${ECR_PROFILE} ecr describe-repositories \
    --repository-names "${LAMBDA_ECR_REPOSITORY}" \
    --region "${AWS_REGION}" > /dev/null 2>&1; then
    echo "ECR repository ${LAMBDA_ECR_REPOSITORY} already exists."
    echo "Deleting all images in the repository..."
    
    # List all images in the repository
    IMAGE_IDS=$(aws --profile ${ECR_PROFILE} ecr list-images \
        --repository-name "${LAMBDA_ECR_REPOSITORY}" \
        --region "${AWS_REGION}" \
        --query 'imageIds[*]' \
        --output json)
    
    # Check if there are images to delete
    if [ -n "$IMAGE_IDS" ] && [ "$IMAGE_IDS" != "[]" ]; then
        # Delete all images
        aws --profile ${ECR_PROFILE} ecr batch-delete-image \
            --repository-name "${LAMBDA_ECR_REPOSITORY}" \
            --region "${AWS_REGION}" \
            --image-ids "$IMAGE_IDS"
        echo "All images deleted from ${LAMBDA_ECR_REPOSITORY}."
    else
        echo "No images found in ${LAMBDA_ECR_REPOSITORY}."
    fi
else
    echo "Creating ECR repository ${LAMBDA_ECR_REPOSITORY}..."
    aws --profile ${ECR_PROFILE} ecr create-repository \
        --repository-name "${LAMBDA_ECR_REPOSITORY}" \
        --region "${AWS_REGION}"
fi

# Build Docker image
SCRIPT_DIR="$( cd "$( dirname "${BASH_SOURCE[0]}" )" >/dev/null 2>&1 && pwd )"
LAMBDA_DIR="$(dirname "$SCRIPT_DIR")/lambda"
cd "$LAMBDA_DIR"

ECR_URI="${AWS_ACCOUNT_ID}.dkr.ecr.${AWS_REGION}.amazonaws.com/${LAMBDA_ECR_REPOSITORY}"

echo "Building Docker image from $LAMBDA_DIR"
docker buildx build \
  --platform linux/amd64 \
  --provenance=false \
  --output type=image,push=true \
  --tag "${ECR_URI}:latest" \
  .

cd "$SCRIPT_DIR"

# Step 2: Update or create Lambda function
if check_lambda_exists; then
    echo "Updating existing Lambda function ${LAMBDA_FUNCTION_NAME}..."
    aws --profile ${LAMBDA_PROFILE} lambda update-function-code \
        --function-name "${LAMBDA_FUNCTION_NAME}" \
        --image-uri "${AWS_ACCOUNT_ID}.dkr.ecr.${AWS_REGION}.amazonaws.com/${LAMBDA_ECR_REPOSITORY}:latest" \
        --no-publish

    aws lambda wait function-updated \
        --function-name ${LAMBDA_FUNCTION_NAME} \
        --region ${AWS_REGION} \
        --profile ${LAMBDA_PROFILE}

    aws --profile ${LAMBDA_PROFILE} lambda update-function-configuration \
        --function-name "${LAMBDA_FUNCTION_NAME}" \
        --role "${LAMBDA_ROLE_ARN}" \
        --timeout 900 \
        --memory-size 2048 \
        --environment Variables="{SAGEMAKER_ENDPOINT_NAME=${ENDPOINT_NAME}}"

    # Wait for function to be active
    aws lambda wait function-active-v2 \
        --function-name ${LAMBDA_FUNCTION_NAME} \
        --region ${AWS_REGION} \
        --profile ${LAMBDA_PROFILE}
else
    echo "Creating Lambda function ${LAMBDA_FUNCTION_NAME}..."
    aws --profile ${LAMBDA_PROFILE} lambda create-function \
        --function-name "${LAMBDA_FUNCTION_NAME}" \
        --package-type Image \
        --code ImageUri="${AWS_ACCOUNT_ID}.dkr.ecr.${AWS_REGION}.amazonaws.com/${LAMBDA_ECR_REPOSITORY}:latest" \
        --role "${LAMBDA_ROLE_ARN}" \
        --timeout 900 \
        --memory-size 2048 \
        --environment Variables="{SAGEMAKER_ENDPOINT_NAME=${ENDPOINT_NAME}}"

    # Wait for function to be active
    aws lambda wait function-active-v2 \
        --function-name ${LAMBDA_FUNCTION_NAME} \
        --region ${AWS_REGION} \
        --profile ${LAMBDA_PROFILE}
fi

# Step 3: Configure S3 trigger permission for Lambda function
echo "Configuring S3 trigger permission for Lambda function ${LAMBDA_FUNCTION_NAME}..."

# Check if permission already exists
PERMISSION_EXISTS=$(aws --profile ${LAMBDA_PROFILE} lambda get-policy \
    --function-name "${LAMBDA_FUNCTION_NAME}" 2>/dev/null | \
    jq -r --arg sid "${STATEMENT_ID}" '.Policy | fromjson | .Statement[] | select(.Sid == $sid)')

if [[ -n "${PERMISSION_EXISTS}" ]]; then
    echo "Permission with statement ID ${STATEMENT_ID} already exists. Removing it..."
    aws --profile ${LAMBDA_PROFILE} lambda remove-permission \
        --function-name "${LAMBDA_FUNCTION_NAME}" \
        --statement-id "${STATEMENT_ID}" || {
        echo "Failed to remove existing permission (continuing...)"
    }
fi

# Add new permission
aws --profile ${LAMBDA_PROFILE} lambda add-permission \
    --function-name "${LAMBDA_FUNCTION_NAME}" \
    --statement-id "${STATEMENT_ID}" \
    --action lambda:InvokeFunction \
    --principal s3.amazonaws.com \
    --source-arn "${BUCKET_ARN}" && \
    echo "Successfully added Lambda permission." || {
    echo "S3 trigger permission failed to add (continuing...)"
}

# Step 4: Configure S3 event notification
echo "Using Lambda ARN: ${LAMBDA_ARN}"
echo "Configuring S3 event notification for bucket ${S3_BUCKET}..."

NOTIFICATION_CONFIG=$(cat <<EOF
{
    "LambdaFunctionConfigurations": [
        {
            "LambdaFunctionArn": "${LAMBDA_ARN}",
            "Events": ["s3:ObjectCreated:*"],
            "Filter": {
                "Key": {
                    "FilterRules": [
                        {
                            "Name": "prefix",
                            "Value": "uploads/"
                        },
                        {
                            "Name": "suffix",
                            "Value": ".docx"
                        }
                    ]
                }
            }
        }
    ]
}
EOF
)

aws --profile ${LAMBDA_PROFILE} s3api put-bucket-notification-configuration \
    --bucket "${S3_BUCKET}" \
    --notification-configuration "${NOTIFICATION_CONFIG}" && \
    echo "Successfully set S3 notification configuration." || {
    echo "S3 notification configuration failed to update (continuing...)"
}

echo "Lambda deployment and S3 trigger setup complete."