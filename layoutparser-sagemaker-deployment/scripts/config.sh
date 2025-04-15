#!/bin/bash

# Configuration file for AWS deployment
# Contains all environment variables needed for the deployment process

# AWS Configuration
export AWS_REGION="us-east-1"                     
export AWS_ACCOUNT_ID="864899869769"            

# S3 Configuration
export S3_BUCKET="aytanai-batch-processing"         
export S3_SAGEMAKER_PREFIX="sagemaker/models/"      
export LOCAL_UPLOADS_DIR="../uploads/mydocs"        
export METADATA_FILE="../uploads/metadata.json"     

# SageMaker Configuration
export SAGEMAKER_MODEL_NAME="layoutparser-model" 
export ENDPOINT_CONFIG_NAME="layoutparser-endpoint-config" 
export ENDPOINT_NAME="layoutparser-endpoint"              
export SAGEMAKER_ROLE_ARN="arn:aws:iam::864899869769:role/service-role/AmazonSageMaker-ExecutionRole-20250325T114201" 
export LOCAL_MODEL_DIR="../sagemaker_model"         

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
export PYTORCH_IMAGE="763104351884.dkr.ecr.${AWS_REGION}.amazonaws.com/pytorch-inference:2.0.0-cpu-py310"

# Lambda ARN for S3 trigger
export LAMBDA_ARN="arn:aws:lambda:${AWS_REGION}:${AWS_ACCOUNT_ID}:function:${LAMBDA_FUNCTION_NAME}"
export BUCKET_ARN="arn:aws:s3:::${S3_BUCKET}"
export STATEMENT_ID="s3-trigger"
