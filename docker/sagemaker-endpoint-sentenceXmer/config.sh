#!/bin/bash

# Configuration file for AWS deployment
# Contains environment variables needed for the SageMaker deployment process

# AWS Configuration
export AWS_REGION="us-east-1"
export AWS_ACCOUNT_ID="864899869769"

# S3 Configuration
export S3_BUCKET="aytanai-batch-processing"
export S3_SAGEMAKER_PREFIX="sagemaker/models/"

# SageMaker Configuration
export SAGEMAKER_MODEL_NAME="faiss-serverless"
export ENDPOINT_CONFIG_NAME="faiss-serverless-config"
export ENDPOINT_NAME="faiss-serverless"
export SAGEMAKER_ROLE_ARN="arn:aws:iam::864899869769:role/service-role/AmazonSageMaker-ExecutionRole-20250325T114201"
export LOCAL_MODEL_DIR="../sagemaker_model"

# TorchServe Environment Variables for SageMaker
export TS_LOG_LOCATION="/tmp/ts.log"
export TS_METRICS_LOG_LOCATION="/tmp/ts_metrics.log"
export TS_ACCESS_LOG_LOCATION="/tmp/access.log"
export TS_MODEL_LOG_LOCATION="/tmp/model.log"
export TS_MODEL_METRICS_LOG_LOCATION="/tmp/model_metrics.log"
export TS_WORKER_TIMEOUT="600"
export TS_DEFAULT_WORKERS_PER_MODEL="1"
export TS_SNAPSHOT_DIR="/tmp"

# AWS CLI profiles
export S3_PROFILE="aytanai-s3-user"
export SAGEMAKER_PROFILE="aytanai-sagemaker-user"

# PyTorch image for SageMaker (AWS-provided)
export PYTORCH_IMAGE="763104351884.dkr.ecr.us-east-1.amazonaws.com/pytorch-inference:1.13.1-cpu-py39"