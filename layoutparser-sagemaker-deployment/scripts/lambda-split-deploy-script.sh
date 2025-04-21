#!/bin/bash
# Exit on error
set -e

# Source environment variables
SCRIPT_DIR="$( cd "$( dirname "${BASH_SOURCE[0]}" )" >/dev/null 2>&1 && pwd )"
source "${SCRIPT_DIR}/config.sh"

# Define repositories
LIBREOFFICE_ECR_REPOSITORY="${LAMBDA_ECR_REPOSITORY}-libreoffice"
TESSERACT_ECR_REPOSITORY="${LAMBDA_ECR_REPOSITORY}-tesseract"
SPACY_ECR_REPOSITORY="${LAMBDA_ECR_REPOSITORY}-spacy"

# --- Helper Functions ---
# Check if a Lambda function exists
check_lambda_exists() {
    aws --profile ${LAMBDA_PROFILE} lambda get-function --function-name "${LAMBDA_FUNCTION_NAME}" > /dev/null 2>&1
    return $?
}

# Function to check if an image exists in ECR
image_exists_in_ecr() {
    local repo_name=$1
    local tag=$2
    
    aws --profile ${ECR_PROFILE} ecr describe-images \
        --repository-name "${repo_name}" \
        --region "${AWS_REGION}" \
        --image-ids imageTag="${tag}" &>/dev/null
    
    return $?
}

# Step 1: Authenticate to Amazon ECR
echo "Authenticating to Amazon ECR..."
aws --profile ${ECR_PROFILE} ecr get-login-password --region "${AWS_REGION}" | docker login --username AWS --password-stdin ${AWS_ACCOUNT_ID}.dkr.ecr.${AWS_REGION}.amazonaws.com

# Step 2: Move to Lambda directory
LAMBDA_DIR="$(dirname "$SCRIPT_DIR")/lambda"
cd "$LAMBDA_DIR"

export DOCKER_BUILDKIT=1

# Step 3: Build and push LibreOffice image
echo "Checking LibreOffice Docker image..."
# Check if repository exists
if ! aws --profile ${ECR_PROFILE} ecr describe-repositories --repository-names "${LIBREOFFICE_ECR_REPOSITORY}" --region "${AWS_REGION}" &>/dev/null; then
    echo "Creating ECR repository ${LIBREOFFICE_ECR_REPOSITORY}..."
    aws --profile ${ECR_PROFILE} ecr create-repository --repository-name "${LIBREOFFICE_ECR_REPOSITORY}" --region "${AWS_REGION}"
    LIBREOFFICE_IMAGE_EXISTS=false
else
    # Check if image with latest tag exists
    if image_exists_in_ecr "${LIBREOFFICE_ECR_REPOSITORY}" "latest"; then
        echo "LibreOffice image already exists in ECR. Skipping build."
        LIBREOFFICE_IMAGE_EXISTS=true
    else
        echo "LibreOffice repository exists but latest image not found."
        LIBREOFFICE_IMAGE_EXISTS=false
    fi
fi

# Build and push LibreOffice image if it doesn't exist
if [ "$LIBREOFFICE_IMAGE_EXISTS" != "true" ]; then
    echo "Building LibreOffice image..."
    docker buildx build \
        --platform linux/amd64 \
        --provenance=false \
        --output type=image,push=true \
        --tag "${AWS_ACCOUNT_ID}.dkr.ecr.${AWS_REGION}.amazonaws.com/${LIBREOFFICE_ECR_REPOSITORY}:latest" \
        --file Dockerfile.libreoffice \
        .
    
    echo "Verifying LibreOffice image..."
    aws --profile ${ECR_PROFILE} ecr describe-images \
        --repository-name "${LIBREOFFICE_ECR_REPOSITORY}" \
        --region "${AWS_REGION}" \
        --query 'imageDetails[*].{Tags:imageTags,Pushed:imagePushedAt}' \
        --output table
else
    echo "Using existing LibreOffice image from ECR."
fi

# Step 4: Build and push Tesseract image
echo "Checking Tesseract Docker image..."
# Check if repository exists
if ! aws --profile ${ECR_PROFILE} ecr describe-repositories --repository-names "${TESSERACT_ECR_REPOSITORY}" --region "${AWS_REGION}" &>/dev/null; then
    echo "Creating ECR repository ${TESSERACT_ECR_REPOSITORY}..."
    aws --profile ${ECR_PROFILE} ecr create-repository --repository-name "${TESSERACT_ECR_REPOSITORY}" --region "${AWS_REGION}"
    TESSERACT_IMAGE_EXISTS=false
else
    # Check if image with latest tag exists
    if image_exists_in_ecr "${TESSERACT_ECR_REPOSITORY}" "latest"; then
        echo "Tesseract image already exists in ECR. Skipping build."
        TESSERACT_IMAGE_EXISTS=true
    else
        echo "Tesseract repository exists but latest image not found."
        TESSERACT_IMAGE_EXISTS=false
    fi
fi

# Build and push Tesseract image if it doesn't exist
if [ "$TESSERACT_IMAGE_EXISTS" != "true" ]; then
    echo "Building Tesseract image..."
    docker buildx build \
        --platform linux/amd64 \
        --provenance=false \
        --output type=image,push=true \
        --tag "${AWS_ACCOUNT_ID}.dkr.ecr.${AWS_REGION}.amazonaws.com/${TESSERACT_ECR_REPOSITORY}:latest" \
        --file Dockerfile.tesseract \
        .
    
    echo "Verifying Tesseract image..."
    aws --profile ${ECR_PROFILE} ecr describe-images \
        --repository-name "${TESSERACT_ECR_REPOSITORY}" \
        --region "${AWS_REGION}" \
        --query 'imageDetails[*].{Tags:imageTags,Pushed:imagePushedAt}' \
        --output table
else
    echo "Using existing Tesseract image from ECR."
fi

# Step 5: Build and push spaCy image
echo "Checking spaCy Docker image..."
# Check if repository exists
if ! aws --profile ${ECR_PROFILE} ecr describe-repositories --repository-names "${SPACY_ECR_REPOSITORY}" --region "${AWS_REGION}" &>/dev/null; then
    echo "Creating ECR repository ${SPACY_ECR_REPOSITORY}..."
    aws --profile ${ECR_PROFILE} ecr create-repository --repository-name "${SPACY_ECR_REPOSITORY}" --region "${AWS_REGION}"
    SPACY_IMAGE_EXISTS=false
else
    # Check if image with latest tag exists
    if image_exists_in_ecr "${SPACY_ECR_REPOSITORY}" "latest"; then
        echo "spaCy image already exists in ECR. Skipping build."
        SPACY_IMAGE_EXISTS=true
    else
        echo "spaCy repository exists but latest image not found."
        SPACY_IMAGE_EXISTS=false
    fi
fi

# Build and push spaCy image if it doesn't exist
if [ "$SPACY_IMAGE_EXISTS" != "true" ]; then
    echo "Building spaCy image..."
    docker buildx build \
        --platform linux/amd64 \
        --provenance=false \
        --output type=image,push=true \
        --tag "${AWS_ACCOUNT_ID}.dkr.ecr.${AWS_REGION}.amazonaws.com/${SPACY_ECR_REPOSITORY}:latest" \
        --file Dockerfile.spacy \
        .
    
    echo "Verifying spaCy image..."
    aws --profile ${ECR_PROFILE} ecr describe-images \
        --repository-name "${SPACY_ECR_REPOSITORY}" \
        --region "${AWS_REGION}" \
        --query 'imageDetails[*].{Tags:imageTags,Pushed:imagePushedAt}' \
        --output table
else
    echo "Using existing spaCy image from ECR."
fi

# Step 6: Build and push Lambda image
echo "Building and pushing Lambda Docker image..."
# Check if repository exists
if ! aws --profile ${ECR_PROFILE} ecr describe-repositories --repository-names "${LAMBDA_ECR_REPOSITORY}" --region "${AWS_REGION}" &>/dev/null; then
    echo "Creating ECR repository ${LAMBDA_ECR_REPOSITORY}..."
    aws --profile ${ECR_PROFILE} ecr create-repository --repository-name "${LAMBDA_ECR_REPOSITORY}" --region "${AWS_REGION}"
fi

# Build Lambda image with explicit build args
echo "Building Lambda image with explicit build args:"
echo "ACCOUNT_ID: ${AWS_ACCOUNT_ID}"
echo "REGION: ${AWS_REGION}"
echo "LIBREOFFICE_REPO: ${LIBREOFFICE_ECR_REPOSITORY}"
echo "TESSERACT_REPO: ${TESSERACT_ECR_REPOSITORY}"
echo "SPACY_REPO: ${SPACY_ECR_REPOSITORY}"

docker buildx build \
    --platform linux/amd64 \
    --provenance=false \
    --output type=image,push=true \
    --tag "${AWS_ACCOUNT_ID}.dkr.ecr.${AWS_REGION}.amazonaws.com/${LAMBDA_ECR_REPOSITORY}:latest" \
    --build-arg ACCOUNT_ID="${AWS_ACCOUNT_ID}" \
    --build-arg REGION="${AWS_REGION}" \
    --build-arg LIBREOFFICE_REPO="${LIBREOFFICE_ECR_REPOSITORY}" \
    --build-arg TESSERACT_REPO="${TESSERACT_ECR_REPOSITORY}" \
    --build-arg SPACY_REPO="${SPACY_ECR_REPOSITORY}" \
    --file Dockerfile.lambda \
    .

# Verify image exists
echo "Verifying Lambda image..."
aws --profile ${ECR_PROFILE} ecr describe-images \
    --repository-name "${LAMBDA_ECR_REPOSITORY}" \
    --region "${AWS_REGION}" \
    --query 'imageDetails[*].{Tags:imageTags,Pushed:imagePushedAt}' \
    --output table

cd "$SCRIPT_DIR" || exit 1

# Step 7: Update or create Lambda function
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
    echo "IMAGE URI = ${AWS_ACCOUNT_ID}.dkr.ecr.${AWS_REGION}.amazonaws.com/${LAMBDA_ECR_REPOSITORY}:latest"
    echo "Role = ${LAMBDA_ROLE_ARN}"
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

# Step 8: Configure S3 trigger permission for Lambda function
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

# Step 9: Configure S3 event notification
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
              "Value": "uploads/rag-data-extraction/"
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
              "Value": "uploads/rag-data-extraction/"
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
              "Value": "uploads/rag-data-extraction/"
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
    echo "S3 notification configuration failed to update, continuing..."
}

echo "Multi-image Lambda deployment and S3 trigger setup complete."