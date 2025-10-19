#!/bin/bash
# Exit on error
set -e

# Source environment variables
SCRIPT_DIR="$( cd "$( dirname "${BASH_SOURCE[0]}" )" >/dev/null 2>&1 && pwd )"
source "${SCRIPT_DIR}/config.sh"

# Validate required environment variables
if [[ -z "${S3_BUCKET}" || -z "${LABEL_STUDIO_URL}" || -z "${LABEL_STUDIO_API_KEY}" ]]; then
    echo "Error: S3_BUCKET, LABEL_STUDIO_URL, and LABEL_STUDIO_API_KEY must be set in config.sh"
    exit 1
fi

# Define repository
LAMBDA_ECR_REPOSITORY="aytanai-label-data"

# Check if a Lambda function exists
check_lambda_exists() {
    aws --profile ${LAMBDA_PROFILE} lambda get-function --function-name "${LAMBDA_FUNCTION_NAME}" > /dev/null 2>&1
    return $?
}

# Step 1: Authenticate to Amazon ECR
echo "Authenticating to Amazon ECR..."
aws --profile ${ECR_PROFILE} ecr get-login-password --region "${AWS_REGION}" | docker login --username AWS --password-stdin ${AWS_ACCOUNT_ID}.dkr.ecr.${AWS_REGION}.amazonaws.com

# Step 2: Build and push Lambda image
export DOCKER_BUILDKIT=1
echo "Building and pushing Lambda Docker image..."
if ! aws --profile ${ECR_PROFILE} ecr describe-repositories --repository-names "${LAMBDA_ECR_REPOSITORY}" --region "${AWS_REGION}" &>/dev/null; then
    echo "Creating ECR repository ${LAMBDA_ECR_REPOSITORY}..."
    aws --profile ${ECR_PROFILE} ecr create-repository --repository-name "${LAMBDA_ECR_REPOSITORY}" --region "${AWS_REGION}"
fi

docker buildx build \
    --platform linux/amd64 \
    --provenance=false \
    --output type=image,push=true \
    --tag "${AWS_ACCOUNT_ID}.dkr.ecr.${AWS_REGION}.amazonaws.com/${LAMBDA_ECR_REPOSITORY}:latest" \
    --build-arg ACCOUNT_ID="${AWS_ACCOUNT_ID}" \
    --build-arg REGION="${AWS_REGION}" \
    --build-arg LIBREOFFICE_REPO="${LIBREOFFICE_ECR_REPOSITORY}" \
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

# Step 3: Update or create Lambda function
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
        --environment "Variables={S3_BUCKET=${S3_BUCKET},LABEL_STUDIO_URL=${LABEL_STUDIO_URL},LABEL_STUDIO_API_KEY=${LABEL_STUDIO_API_KEY}}"
else
    echo "Creating Lambda function ${LAMBDA_FUNCTION_NAME}..."
    aws --profile ${LAMBDA_PROFILE} lambda create-function \
        --function-name "${LAMBDA_FUNCTION_NAME}" \
        --package-type Image \
        --code ImageUri="${AWS_ACCOUNT_ID}.dkr.ecr.${AWS_REGION}.amazonaws.com/${LAMBDA_ECR_REPOSITORY}:latest" \
        --role "${LAMBDA_ROLE_ARN}" \
        --timeout 900 \
        --memory-size 2048 \
        --environment "Variables={S3_BUCKET=${S3_BUCKET},LABEL_STUDIO_URL=${LABEL_STUDIO_URL},LABEL_STUDIO_API_KEY=${LABEL_STUDIO_API_KEY}}"

    aws lambda wait function-active-v2 \
        --function-name ${LAMBDA_FUNCTION_NAME} \
        --region ${AWS_REGION} \
        --profile ${LAMBDA_PROFILE}
fi

# Step 4: Configure S3 trigger permission
echo "Configuring S3 trigger permission for Lambda function ${LAMBDA_FUNCTION_NAME}..."
PERMISSION_EXISTS=$(aws --profile ${LAMBDA_PROFILE} lambda get-policy \
    --function-name "${LAMBDA_FUNCTION_NAME}" 2>/dev/null | \
    jq -r --arg sid "${STATEMENT_ID}" '.Policy | fromjson | .Statement[] | select(.Sid == $sid)')

if [[ -n "${PERMISSION_EXISTS}" ]]; then
    echo "Permission with statement ID ${STATEMENT_ID} already exists. Removing it..."
    aws --profile ${LAMBDA_PROFILE} lambda remove-permission \
        --function-name "${LAMBDA_FUNCTION_NAME}" \
        --statement-id "${STATEMENT_ID}" || {
        echo "Failed to remove existing permission, continuing..."
    }
fi

aws --profile ${LAMBDA_PROFILE} lambda add-permission \
    --function-name "${LAMBDA_FUNCTION_NAME}" \
    --statement-id "${STATEMENT_ID}" \
    --action lambda:InvokeFunction \
    --principal s3.amazonaws.com \
    --source-arn "${BUCKET_ARN}" && \
    echo "Successfully added Lambda permission." || {
    echo "S3 trigger permission failed to add, continuing..."
}

# Step 5: Configure S3 event notification
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
              "Value": "uploads/labeling/raw/"
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
              "Value": "uploads/labeling/raw/"
            },
            {
              "Name": "suffix",
              "Value": ".pdf"
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

echo "Lambda deployment and S3 trigger setup complete."