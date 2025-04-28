#!/bin/bash

# Exit on any error
set -e

# Check if AWS CLI is installed
if ! command -v aws &> /dev/null; then
    echo "AWS CLI is not installed. Please install it first."
    exit 1
fi

# Source the configuration file
if [ ! -f "config.sh" ]; then
    echo "config.sh not found!"
    exit 1
fi
source ./config.sh

# Validate required environment variables
required_vars=(
    "AWS_REGION"
    "AWS_ACCOUNT_ID"
    "SAGEMAKER_ROLE_ARN"
    "S3_BUCKET"
    "SAGEMAKER_PROFILE"
    "S3_PROFILE"
    "SAGEMAKER_MODEL_NAME"
    "ENDPOINT_CONFIG_NAME"
    "ENDPOINT_NAME"
    "LOCAL_MODEL_DIR"
    "PYTORCH_IMAGE"
)
for var in "${required_vars[@]}"; do
    if [ -z "${!var}" ]; then
        echo "Error: $var is not set in config.sh"
        exit 1
    fi
done

# Set variables
MODEL_NAME="${SAGEMAKER_MODEL_NAME}"
ENDPOINT_CONFIG_NAME="${ENDPOINT_CONFIG_NAME}"
ENDPOINT_NAME="${ENDPOINT_NAME}"
IMAGE_URI="${PYTORCH_IMAGE}"
MODEL_S3_PATH="s3://${S3_BUCKET}/${S3_SAGEMAKER_PREFIX}model.tar.gz"
MODEL_DIR="${LOCAL_MODEL_DIR}"
MODEL_TAR="model.tar.gz"

# Helper Functions
check_endpoint_exists() {
    aws --profile "${SAGEMAKER_PROFILE}" sagemaker describe-endpoint --endpoint-name "${ENDPOINT_NAME}" --region "${AWS_REGION}" > /dev/null 2>&1
    return $?
}

check_endpoint_config_exists() {
    aws --profile "${SAGEMAKER_PROFILE}" sagemaker describe-endpoint-config --endpoint-config-name "${ENDPOINT_CONFIG_NAME}" --region "${AWS_REGION}" > /dev/null 2>&1
    return $?
}

check_model_exists() {
    aws --profile "${SAGEMAKER_PROFILE}" sagemaker describe-model --model-name "${MODEL_NAME}" --region "${AWS_REGION}" > /dev/null 2>&1
    return $?
}

wait_for_endpoint_ready() {
    echo "Checking status of endpoint: ${ENDPOINT_NAME}..."
    STATUS=$(aws --profile "${SAGEMAKER_PROFILE}" sagemaker describe-endpoint \
        --endpoint-name "${ENDPOINT_NAME}" \
        --region "${AWS_REGION}" \
        --query 'EndpointStatus' \
        --output text 2>/dev/null)
    
    if [ "$STATUS" == "Creating" ] || [ "$STATUS" == "Updating" ]; then
        echo "Endpoint is in progress (${STATUS}). Waiting for it to complete..."
        aws --profile "${SAGEMAKER_PROFILE}" sagemaker wait endpoint-in-service \
            --endpoint-name "${ENDPOINT_NAME}" \
            --region "${AWS_REGION}"
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

# Create required folder structure
echo "Creating folder structure..."
mkdir -p "${MODEL_DIR}/code"
mkdir -p "${MODEL_DIR}/model"
# Copy necessary files
cp inference.py requirements.txt "${MODEL_DIR}/code/"
cp -r all-MiniLM-L6-v2/ "${MODEL_DIR}/all-MiniLM-L6-v2/"

# Create model.tar.gz
echo "Creating ${MODEL_TAR}..."
cd "${MODEL_DIR}"
tar -czvf "${MODEL_TAR}" code/ all-MiniLM-L6-v2/
cd -

# Upload model to S3
echo "Uploading model to ${MODEL_S3_PATH}..."
aws --profile "${S3_PROFILE}" s3 cp "${MODEL_DIR}/${MODEL_TAR}" "${MODEL_S3_PATH}"

# Clean up temporary files
rm -rf "${MODEL_DIR}/${MODEL_TAR}"

# Clean up existing SageMaker resources
echo "Checking existing SageMaker resources..."

if check_endpoint_exists; then
    echo "Deleting existing SageMaker endpoint ${ENDPOINT_NAME}..."
    wait_for_endpoint_ready
    aws --profile "${SAGEMAKER_PROFILE}" sagemaker delete-endpoint --endpoint-name "${ENDPOINT_NAME}" --region "${AWS_REGION}" || echo "Failed to delete endpoint, proceeding..."
    aws --profile "${SAGEMAKER_PROFILE}" sagemaker wait endpoint-deleted --endpoint-name "${ENDPOINT_NAME}" --region "${AWS_REGION}" || echo "Continuing after wait..."
fi

if check_endpoint_config_exists; then
    echo "Deleting existing SageMaker endpoint config ${ENDPOINT_CONFIG_NAME}..."
    aws --profile "${SAGEMAKER_PROFILE}" sagemaker delete-endpoint-config --endpoint-config-name "${ENDPOINT_CONFIG_NAME}" --region "${AWS_REGION}" || echo "Failed to delete endpoint config, proceeding..."
fi

if check_model_exists; then
    echo "Deleting existing SageMaker model ${MODEL_NAME}..."
    aws --profile "${SAGEMAKER_PROFILE}" sagemaker delete-model --model-name "${MODEL_NAME}" --region "${AWS_REGION}" || echo "Failed to delete model, proceeding..."
fi



max_concurrency=3
echo "Using max concurrency: $max_concurrency"

# Create SageMaker model
echo "Creating SageMaker model ${MODEL_NAME}..."
aws --profile "${SAGEMAKER_PROFILE}" sagemaker create-model \
    --model-name "${MODEL_NAME}" \
    --primary-container "{
        \"Image\": \"${IMAGE_URI}\",
        \"ModelDataUrl\": \"${MODEL_S3_PATH}\",
        \"Environment\": {
            \"SAGEMAKER_PROGRAM\": \"inference.py\",
            \"SAGEMAKER_SUBMIT_DIRECTORY\": \"/opt/ml/model/code\",
            \"TS_LOG_LOCATION\": \"${TS_LOG_LOCATION}\",
            \"TS_METRICS_LOG_LOCATION\": \"${TS_METRICS_LOG_LOCATION}\",
            \"TS_ACCESS_LOG_LOCATION\": \"${TS_ACCESS_LOG_LOCATION}\",
            \"TS_MODEL_LOG_LOCATION\": \"${TS_MODEL_LOG_LOCATION}\",
            \"TS_MODEL_METRICS_LOG_LOCATION\": \"${TS_MODEL_METRICS_LOG_LOCATION}\",
            \"TS_WORKER_TIMEOUT\": \"${TS_WORKER_TIMEOUT}\",
            \"TS_DEFAULT_WORKERS_PER_MODEL\": \"${TS_DEFAULT_WORKERS_PER_MODEL}\",
            \"TS_SNAPSHOT_DIR\": \"${TS_SNAPSHOT_DIR}\"
        }
    }" \
    --execution-role-arn "${SAGEMAKER_ROLE_ARN}" \
    --region "${AWS_REGION}"

# Create endpoint configuration
echo "Creating endpoint configuration ${ENDPOINT_CONFIG_NAME}..."
aws --profile "${SAGEMAKER_PROFILE}" sagemaker create-endpoint-config \
    --endpoint-config-name "${ENDPOINT_CONFIG_NAME}" \
    --production-variants "[{\"VariantName\": \"AllTraffic\", \"ModelName\": \"${MODEL_NAME}\", \"ServerlessConfig\": {\"MemorySizeInMB\": 3072, \"MaxConcurrency\": $max_concurrency}}]" \
    --region "${AWS_REGION}"

# Create endpoint
echo "Creating endpoint ${ENDPOINT_NAME}..."
aws --profile "${SAGEMAKER_PROFILE}" sagemaker create-endpoint \
    --endpoint-name "${ENDPOINT_NAME}" \
    --endpoint-config-name "${ENDPOINT_CONFIG_NAME}" \
    --region "${AWS_REGION}"

# Wait for endpoint creation
echo "Waiting for endpoint to be in service..."
wait_for_endpoint_ready

echo "Deployment completed successfully!"
echo "Endpoint name: ${ENDPOINT_NAME}"
echo "Model name: ${MODEL_NAME}"
echo "Endpoint configuration name: ${ENDPOINT_CONFIG_NAME}"