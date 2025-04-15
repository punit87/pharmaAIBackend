#!/bin/bash

# Setup script to set execution permissions for all deployment scripts
# Run this first after downloading the scripts

# Exit on error
set -e

echo "Setting execution permissions for all scripts..."

SCRIPT_DIR="$( cd "$( dirname "${BASH_SOURCE[0]}" )" >/dev/null 2>&1 && pwd )"

# Make all scripts executable
chmod +x "${SCRIPT_DIR}/config.sh"
chmod +x "${SCRIPT_DIR}/deploy.sh"
chmod +x "${SCRIPT_DIR}/s3-setup-script.sh"
chmod +x "${SCRIPT_DIR}/sagemaker-deploy-script.sh"
chmod +x "${SCRIPT_DIR}/lambda-deploy-script.sh"

echo "Setting environenment variables for the scripts"
./config.sh
echo "Enviroment variables set"
echo "Execution permissions set. You can now run individual scripts or the full deployment."
echo "For full deployment: ./deploy.sh"
echo "For individual components:"
echo "  - S3 setup: ./s3-setup-script.sh"
echo "  - SageMaker deployment: ./sagemaker-deploy-script.sh"
echo "  - Lambda deployment: ./lambda-deploy-script.sh"
