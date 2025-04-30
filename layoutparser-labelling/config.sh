#!/bin/bash

# Configuration file for AWS deployment
# Contains environment variables needed for the deployment process

# AWS Configuration
export AWS_REGION="us-east-1"
export AWS_ACCOUNT_ID="864899869769"

# S3 Configuration
export S3_BUCKET="aytanai-batch-processing"

# Lambda Configuration
export LAMBDA_FUNCTION_NAME="lambda_label_data"
export LAMBDA_ECR_REPOSITORY="aytanai-label-data"
export LAMBDA_ROLE_ARN="arn:aws:iam::864899869769:role/service-role/inferenceLambda-role-i8fz568r"

# AWS CLI profiles
export S3_PROFILE="aytanai-s3-user"
export ECR_PROFILE="aytanai-ecr-user"
export LAMBDA_PROFILE="aytanai-lambda-user"

# Lambda ARN for S3 trigger
export LAMBDA_ARN="arn:aws:lambda:${AWS_REGION}:${AWS_ACCOUNT_ID}:function:${LAMBDA_FUNCTION_NAME}"
export BUCKET_ARN="arn:aws:s3:::${S3_BUCKET}"
export STATEMENT_ID="s3-trigger"

# LibreOffice ECR Repository
export LIBREOFFICE_ECR_REPOSITORY="aytanai-batch-process-libreoffice"

# Label Studio Configuration
export LABEL_STUDIO_URL="http://ec2-34-227-149-114.compute-1.amazonaws.com:8080"
export LABEL_STUDIO_API_KEY="543048a5251e43a0845c56493097cb1dbd54b67f"