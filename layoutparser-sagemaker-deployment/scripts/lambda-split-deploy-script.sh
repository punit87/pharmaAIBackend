#!/bin/bash

# Lambda Function Deployment and S3 Trigger Setup with Multi-image Architecture
# Handles:
#   - Building and pushing Docker images (LibreOffice, Tesseract, Lambda) to ECR
#   - Creating or updating Lambda function
#   - Setting up S3 trigger for Lambda function

# Exit on error
set -e

# Source environment variables if not already loaded
if [ -z "$AWS_REGION" ]; then
  SCRIPT_DIR="$( cd "$( dirname "${BASH_SOURCE[0]}" )" >/dev/null 2>&1 && pwd )"
  source "${SCRIPT_DIR}/config.sh"
fi

# Additional environment variables for new repositories
LIBREOFFICE_ECR_REPOSITORY="${LAMBDA_ECR_REPOSITORY}-libreoffice"
TESSERACT_ECR_REPOSITORY="${LAMBDA_ECR_REPOSITORY}-tesseract"

# --- Helper Functions ---
# Check if a Lambda function exists
check_lambda_exists() {
    aws --profile ${LAMBDA_PROFILE} lambda get-function --function-name "${LAMBDA_FUNCTION_NAME}" > /dev/null 2>&1
    return $?
}

# Function for ECR repository management
manage_ecr_repo() {
    local repo_name=$1
    local image_tag=$2
    local dockerfile=$3
    local build_args=$4
    local force_rebuild=$5
    
    echo "Managing ECR repository: ${repo_name}"
    
    # Check if repository exists
    if aws --profile ${ECR_PROFILE} ecr describe-repositories \
        --repository-names "${repo_name}" \
        --region "${AWS_REGION}" > /dev/null 2>&1; then
        echo "ECR repository ${repo_name} already exists."
        
        # List all images in the repository
        IMAGE_IDS=$(aws --profile ${ECR_PROFILE} ecr list-images \
            --repository-name "${repo_name}" \
            --region "${AWS_REGION}" \
            --query 'imageIds[*]' \
            --output json)
        
        if [ "$force_rebuild" = "true" ]; then
            echo "Force rebuild enabled. Deleting all images in ${repo_name}..."
            if [ -n "$IMAGE_IDS" ] && [ "$IMAGE_IDS" != "[]" ]; then
                aws --profile ${ECR_PROFILE} ecr batch-delete-image \
                    --repository-name "${repo_name}" \
                    --region "${AWS_REGION}" \
                    --image-ids "$IMAGE_IDS"
                echo "All images deleted from ${repo_name}."
            else
                echo "No images found in ${repo_name}."
            fi
        else
            if [ -n "$IMAGE_IDS" ] && [ "$IMAGE_IDS" != "[]" ]; then
                echo "Images found in ${repo_name}. Skipping build and push."
                return
            else
                echo "No images found in ${repo_name}. Proceeding with build and push."
            fi
        fi
    else
        echo "Creating ECR repository ${repo_name}..."
        aws --profile ${ECR_PROFILE} ecr create-repository \
            --repository-name "${repo_name}" \
            --region "${AWS_REGION}"
    fi
    
    # Build and push Docker image
    local ecr_uri="${AWS_ACCOUNT_ID}.dkr.ecr.${AWS_REGION}.amazonaws.com/${repo_name}"
    
    echo "Building and pushing Docker image for ${repo_name}"
    if [ -n "$build_args" ]; then
        docker buildx build \
          --platform linux/amd64 \
          --provenance=false \
          --output type=image,push=true \
          --tag "${ecr_uri}:${image_tag}" \
          ${build_args} \
          --file "${dockerfile}" \
          .  # <-- THIS IS THE MISSING BUILD CONTEXT
    else
        docker buildx build \
          --platform linux/amd64 \
          --provenance=false \
          --output type=image,push=true \
          --tag "${ecr_uri}:${image_tag}" \
          --file "${dockerfile}" \
          .  # <-- THIS IS THE MISSING BUILD CONTEXT
    fi
}

echo "==== Lambda Deployment and S3 Trigger Setup with Multi-image Architecture ===="

# Step 1: Authenticate to Amazon ECR
echo "Authenticating to Amazon ECR..."
aws --profile ${ECR_PROFILE} ecr get-login-password --region "${AWS_REGION}" | docker login --username AWS --password-stdin ${AWS_ACCOUNT_ID}.dkr.ecr.${AWS_REGION}.amazonaws.com

# Step 2: Move to Lambda directory
SCRIPT_DIR="$( cd "$( dirname "${BASH_SOURCE[0]}" )" >/dev/null 2>&1 && pwd )"
LAMBDA_DIR="$(dirname "$SCRIPT_DIR")/lambda"
cd "$LAMBDA_DIR"

export DOCKER_BUILDKIT=1

# Step 3: Build and push LibreOffice image
echo "Building and pushing LibreOffice Docker image..."
manage_ecr_repo "${LIBREOFFICE_ECR_REPOSITORY}" "latest" "Dockerfile.libreoffice" "false"

# Step 4: Build and push Tesseract image
echo "Building and pushing Tesseract Docker image..."
manage_ecr_repo "${TESSERACT_ECR_REPOSITORY}" "latest" "Dockerfile.tesseract" "false"

# Step 5: Build and push Lambda image

echo "Building and pushing Lambda Docker image..."
cd "$LAMBDA_DIR" || exit 1
echo "${AWS_ACCOUNT_ID}.dkr.ecr.${AWS_REGION}.amazonaws.com/${LAMBDA_ECR_REPOSITORY}:latest"
docker buildx build \
  --platform linux/amd64 \
  --provenance=false \
  --output type=image,push=true \
  --tag "${AWS_ACCOUNT_ID}.dkr.ecr.${AWS_REGION}.amazonaws.com/${LAMBDA_ECR_REPOSITORY}:latest" \
  --build-arg ACCOUNT_ID="${AWS_ACCOUNT_ID}" \
  --build-arg REGION="${AWS_REGION}" \
  --build-arg TESSERACT_REPO="${TESSERACT_ECR_REPOSITORY}" \
  --build-arg LIBREOFFICE_REPO="${LIBREOFFICE_ECR_REPOSITORY}" \
  --file Dockerfile.lambda \
  .

cd "$SCRIPT_DIR" || exit 1

# Step 6: Update or create Lambda function
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
        --environment Variables="{SAGEMAKER_ENDPOINT_NAME=${ENDPOINT_NAME},DB_NAME=${DB_NAME},DB_USER=${DB_USER},DB_PASSWORD=${DB_PASSWORD},DB_HOST=${DB_HOST},DB_PORT=${DB_PORT},DB_SSLMODE=${DB_SSLMODE}}"

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
        --environment Variables="{SAGEMAKER_ENDPOINT_NAME=${ENDPOINT_NAME},DB_NAME=${DB_NAME},DB_USER=${DB_USER},DB_PASSWORD=${DB_PASSWORD},DB_HOST=${DB_HOST},DB_PORT=${DB_PORT},DB_SSLMODE=${DB_SSLMODE}}"

    # Wait for function to be active
    aws lambda wait function-active-v2 \
        --function-name ${LAMBDA_FUNCTION_NAME} \
        --region ${AWS_REGION} \
        --profile ${LAMBDA_PROFILE}
fi

# Step 7: Configure S3 trigger permission for Lambda function
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
        echo "Failed to remove existing permission ,continuing..."
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
    echo "S3 trigger permission failed to add ,continuing..."
}

# Step 8: Configure S3 event notification
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
              "Value": "Uploads/rag-data-extraction/"
            },
            {
              "Name": "suffix",
              "Value": ".docx"
            }
          ]
        }
      }
    },
    {
      "LambdaFunctionArn": "${LAMBDA_ARN}",
      "Events": ["s3:ObjectCreated:*"],
      "Filter": {
        "Key": {
          "FilterRules": [
            {
              "Name": "prefix",
              "Value": "Uploads/rag-data-extraction/"
            },
            {
              "Name": "suffix",
              "Value": ".pdf"
            }
          ]
        }
      }
    },
    {
      "LambdaFunctionArn": "${LAMBDA_ARN}",
      "Events": ["s3:ObjectCreated:*"],
      "Filter": {
        "Key": {
          "FilterRules": [
            {
              "Name": "prefix",
              "Value": "Uploads/rag-data-extraction/"
            },
            {
              "Name": "suffix",
              "Value": ".doc"
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
    echo "S3 notification configuration failed to update ,continuing..."
}

echo "Multi-image Lambda deployment and S3 trigger setup complete."