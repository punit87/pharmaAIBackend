#!/bin/bash

# Configuration file for AWS deployment
# Contains all environment variables needed for the deployment process

# AWS Configuration
export AWS_REGION="us-east-1"
export AWS_ACCOUNT_ID="864899869769"

# S3 Configuration
export S3_BUCKET="aytanai-batch-processing"
export S3_SAGEMAKER_PREFIX="sagemaker/models/"
export LOCAL_UPLOADS_DIR="../Uploads/mydocs"
export METADATA_FILE="../Uploads/metadata.json"

# SageMaker Configuration
export SAGEMAKER_MODEL_NAME="layoutparser-model"
export ENDPOINT_CONFIG_NAME="layoutparser-endpoint-config"
export ENDPOINT_NAME="layoutparser-endpoint"
export SAGEMAKER_ROLE_ARN="arn:aws:iam::864899869769:role/service-role/AmazonSageMaker-ExecutionRole-20250325T114201"
export LOCAL_MODEL_DIR="../sagemaker_model"
export SAGEMAKER_ENDPOINT_NAME=layoutparser-endpoint
# TorchServe Environment Variables for SageMaker
export TS_LOG_LOCATION="/tmp/ts.log"
export TS_METRICS_LOG_LOCATION="/tmp/ts_metrics.log"
export TS_ACCESS_LOG_LOCATION="/tmp/access.log"
export TS_MODEL_LOG_LOCATION="/tmp/model.log"
export TS_MODEL_METRICS_LOG_LOCATION="/tmp/model_metrics.log"
export TS_WORKER_TIMEOUT="600"
export TS_DEFAULT_WORKERS_PER_MODEL="1"
export TS_SNAPSHOT_DIR="/tmp"

# Lambda Configuration
export LAMBDA_FUNCTION_NAME="lambda_batch_process"
export LAMBDA_ECR_REPOSITORY="aytanai-batch-process"
export LAMBDA_ROLE_ARN="arn:aws:iam::864899869769:role/service-role/inferenceLambda-role-i8fz568r"

# AWS CLI profiles
export S3_PROFILE="aytanai-s3-user"
export SAGEMAKER_PROFILE="aytanai-sagemaker-user"
export ECR_PROFILE="aytanai-ecr-user"
export LAMBDA_PROFILE="aytanai-lambda-user"

# PyTorch image for SageMaker (AWS-provided)
export PYTORCH_IMAGE="763104351884.dkr.ecr.us-east-1.amazonaws.com/pytorch-inference:1.13.1-cpu-py39"

# Lambda ARN for S3 trigger
export LAMBDA_ARN="arn:aws:lambda:${AWS_REGION}:${AWS_ACCOUNT_ID}:function:${LAMBDA_FUNCTION_NAME}"
export BUCKET_ARN="arn:aws:s3:::${S3_BUCKET}"
export STATEMENT_ID="s3-trigger"

export DB_NAME=neondb
export DB_USER=neondb_owner
export DB_PASSWORD=npg_a7UTVgtl3xWk
export DB_HOST=ep-red-bush-a43597op-pooler.us-east-1.aws.neon.tech
export DB_PORT=5432
export DB_SSLMODE=require
