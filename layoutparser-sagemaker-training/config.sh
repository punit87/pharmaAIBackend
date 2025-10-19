#!/bin/bash

# 🔹 This file sets environment variables for the LayoutParser training job
# 🔹 Must be sourced using: source config.sh
# 🔹 Ensure the following variables are set correctly:



# Environment variables for layout-parser training job
export ENV_TRAIN_LP_S3_BUCKET="aytanai-batch-processing"
export ENV_TRAIN_LP_S3_PREFIX="uploads/model-training/layout-parser/"
export ENV_TRAIN_LP_AWS_REGION="us-east-1"
export ENV_TRAIN_LP_AWS_ACCOUNT_ID="864899869769"
export ENV_TRAIN_LP_SAGEMAKER_ROLE_ARN="arn:aws:iam::864899869769:role/service-role/AmazonSageMaker-ExecutionRole-20250325T114201"
export ENV_TRAIN_LP_SAGEMAKER_PROFILE="aytanai-sagemaker-user"
export ENV_TRAIN_LP_LAMBDA_FUNCTION="layoutparser-training-launcher"
export ENV_TRAIN_LP_LAMBDA_ROLE_ARN="arn:aws:iam::864899869769:role/service-role/inferenceLambda-role-i8fz568r"

# These are also used by train.py and should be kept
export ENV_TRAIN_LP_CHECKPOINT_DIR="/opt/ml/checkpoints"
export ENV_TRAIN_LP_OUTPUT_DIR="/opt/ml/model"
export ENV_TRAIN_LP_PRETRAINED_DIR="/opt/ml/model/pretrained"
export ENV_TRAIN_LP_DEVICE="cuda"
export ENV_TRAIN_LP_LABEL_MAP='{"0": "figure", "1": "list", "2": "table", "3": "text", "4": "title"}'

export ENV_S3_PROFILE="aytanai-s3-user"
export ENV_SAGEMAKER_PROFILE="aytanai-sagemaker-user"
export ENV_ECR_PROFILE="aytanai-ecr-user"
export ENV_LAMBDA_PROFILE="aytanai-lambda-user"