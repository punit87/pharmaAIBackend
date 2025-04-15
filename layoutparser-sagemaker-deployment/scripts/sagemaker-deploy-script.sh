#!/bin/bash

# SageMaker Deployment Script
# Handles:
#   - Packaging model files into tar.gz
#   - Uploading model artifact to S3
#   - Deleting existing SageMaker resources
#   - Creating SageMaker model
#   - Creating endpoint configuration
#   - Creating serverless endpoint

# Exit on error
set -e

# Source environment variables if not already loaded
if [ -z "$AWS_REGION" ]; then
  SCRIPT_DIR="$( cd "$( dirname "${BASH_SOURCE[0]}" )" >/dev/null 2>&1 && pwd )"
  source "${SCRIPT_DIR}/config.sh"
fi

# --- Configuration ---
MODEL_DIR="../sagemaker_model"
MODEL_TAR="model.tar.gz"
S3_MODEL_PATH="s3://${S3_BUCKET}/${S3_SAGEMAKER_PREFIX}${SAGEMAKER_MODEL_NAME}/${MODEL_TAR}"

# --- Helper Functions ---
# Check if a SageMaker endpoint exists
check_endpoint_exists() {
    aws --profile ${SAGEMAKER_PROFILE} sagemaker describe-endpoint --endpoint-name "${ENDPOINT_NAME}" > /dev/null 2>&1
    return $?
}

# Check if a SageMaker endpoint config exists
check_endpoint_config_exists() {
    aws --profile ${SAGEMAKER_PROFILE} sagemaker describe-endpoint-config --endpoint-config-name "${ENDPOINT_CONFIG_NAME}" > /dev/null 2>&1
    return $?
}

# Check if a SageMaker model exists
check_model_exists() {
    aws --profile ${SAGEMAKER_PROFILE} sagemaker describe-model --model-name "${SAGEMAKER_MODEL_NAME}" > /dev/null 2>&1
    return $?
}

# Wait for endpoint to be ready
wait_for_endpoint_ready() {
    echo "Checking status of endpoint: ${ENDPOINT_NAME}..."

    STATUS=$(aws --profile ${SAGEMAKER_PROFILE} sagemaker describe-endpoint \
        --endpoint-name "${ENDPOINT_NAME}" \
        --query 'EndpointStatus' \
        --output text 2>/dev/null)
    
    if [ "$STATUS" == "Creating" ] || [ "$STATUS" == "Updating" ]; then
        echo "Endpoint is in progress (${STATUS}). Waiting for it to complete..."
        aws --profile ${SAGEMAKER_PROFILE} sagemaker wait endpoint-in-service \
            --endpoint-name "${ENDPOINT_NAME}"
        echo "Endpoint is now in service!"
    elif [ "$STATUS" == "InService" ]; then
        echo "Endpoint is already InService."
    elif [ -z "$STATUS" ]; then
        echo "Endpoint does not exist."
    else
        echo "Endpoint status is: $STATUS"
    fi
}

echo "==== SageMaker Deployment ===="

# Package model files into tar.gz
echo "Packaging model files into ${MODEL_TAR}..."
cd "${MODEL_DIR}"
tar -czf "${MODEL_TAR}" config.yml model_final.pth code/
cd -

# Upload model artifact to S3 using S3_PROFILE
echo "Uploading model artifact to ${S3_MODEL_PATH}..."
aws --profile ${S3_PROFILE} s3 cp "${MODEL_DIR}/${MODEL_TAR}" "${S3_MODEL_PATH}"

# Clean up local tar file
rm "${MODEL_DIR}/${MODEL_TAR}"

# Clean up existing SageMaker resources
echo "Checking existing SageMaker resources..."

if check_endpoint_exists; then
    echo "Deleting existing SageMaker endpoint ${ENDPOINT_NAME}..."
    wait_for_endpoint_ready
    aws --profile ${SAGEMAKER_PROFILE} sagemaker delete-endpoint --endpoint-name "${ENDPOINT_NAME}" || echo "Failed to delete endpoint, proceeding..."
    aws --profile ${SAGEMAKER_PROFILE} sagemaker wait endpoint-deleted --endpoint-name "${ENDPOINT_NAME}" || echo "Continuing after wait..."
fi

if check_endpoint_config_exists; then
    echo "Deleting existing SageMaker endpoint config ${ENDPOINT_CONFIG_NAME}..."
    aws --profile ${SAGEMAKER_PROFILE} sagemaker delete-endpoint-config --endpoint-config-name "${ENDPOINT_CONFIG_NAME}" || echo "Failed to delete endpoint config, proceeding..."
fi

if check_model_exists; then
    echo "Deleting existing SageMaker model ${SAGEMAKER_MODEL_NAME}..."
    aws --profile ${SAGEMAKER_PROFILE} sagemaker delete-model --model-name "${SAGEMAKER_MODEL_NAME}" || echo "Failed to delete model, proceeding..."
fi

# Create SageMaker model
echo "Creating SageMaker model..."
aws --profile ${SAGEMAKER_PROFILE} sagemaker create-model \
    --model-name "${SAGEMAKER_MODEL_NAME}" \
    --primary-container Image="${PYTORCH_IMAGE}",ModelDataUrl="${S3_MODEL_PATH}" \
    --execution-role-arn "${SAGEMAKER_ROLE_ARN}"

# Create serverless endpoint configuration
echo "Creating SageMaker endpoint configuration..."
aws --profile ${SAGEMAKER_PROFILE} sagemaker create-endpoint-config \
    --endpoint-config-name "${ENDPOINT_CONFIG_NAME}" \
    --production-variants '[{"VariantName":"AllTraffic","ModelName":"'"${SAGEMAKER_MODEL_NAME}"'","ServerlessConfig":{"MemorySizeInMB":2048,"MaxConcurrency":1}}]'

# Create serverless endpoint
echo "Creating SageMaker serverless endpoint..."
aws --profile ${SAGEMAKER_PROFILE} sagemaker create-endpoint \
    --endpoint-name "${ENDPOINT_NAME}" \
    --endpoint-config-name "${ENDPOINT_CONFIG_NAME}"

echo "SageMaker endpoint ${ENDPOINT_NAME} is being created."
echo "Check status with: aws --profile ${SAGEMAKER_PROFILE} sagemaker describe-endpoint --endpoint-name ${ENDPOINT_NAME}"

# Wait for endpoint to be in service
wait_for_endpoint_ready

echo "SageMaker deployment complete."