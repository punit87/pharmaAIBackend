#!/bin/bash

# Parent deployment script that calls individual component scripts
# Usage: ./deploy.sh [options]
#   Options:
#     --skip-s3       Skip S3 setup and file uploads
#     --skip-model    Skip SageMaker model deployment
#     --skip-lambda   Skip Lambda function deployment
#     --help          Show this help message

# Exit on error
set -e

# Script directory
SCRIPT_DIR="$( cd "$( dirname "${BASH_SOURCE[0]}" )" >/dev/null 2>&1 && pwd )"

# Parse command line arguments
SKIP_S3=false
SKIP_MODEL=false
SKIP_LAMBDA=false

for arg in "$@"; do
  case $arg in
    --skip-s3)
      SKIP_S3=true
      shift
      ;;
    --skip-model)
      SKIP_MODEL=true
      shift
      ;;
    --skip-lambda)
      SKIP_LAMBDA=true
      shift
      ;;
    --help)
      echo "Usage: ./deploy.sh [options]"
      echo "  Options:"
      echo "    --skip-s3       Skip S3 setup and file uploads"
      echo "    --skip-model    Skip SageMaker model deployment"
      echo "    --skip-lambda   Skip Lambda function deployment"
      echo "    --help          Show this help message"
      exit 0
      ;;
  esac
done

# Source environment variables
echo "Loading configuration..."
source "${SCRIPT_DIR}/config.sh"

# Run individual scripts
if [ "$SKIP_S3" = false ]; then
  echo "===== RUNNING S3 SETUP ====="
  "${SCRIPT_DIR}/s3-setup-script.sh"
fi

if [ "$SKIP_MODEL" = false ]; then
  echo "===== RUNNING SAGEMAKER DEPLOYMENT ====="
  "${SCRIPT_DIR}/sagemaker-deploy-script.sh"
fi

if [ "$SKIP_LAMBDA" = false ]; then
  echo "===== RUNNING LAMBDA DEPLOYMENT ====="
  "${SCRIPT_DIR}/lambda-deploy-script.sh"
fi

echo "Deployment complete!"
echo "SageMaker endpoint: ${ENDPOINT_NAME}"
echo "Lambda function: ${LAMBDA_FUNCTION_NAME}"
echo "S3 trigger configured for uploads/*.docx"
