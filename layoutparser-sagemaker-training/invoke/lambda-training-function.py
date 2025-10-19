"""
🔹 Lambda function for SageMaker training job.
🔹 Accepts POST request with optional hyperparameters.
🔹 Environment variables must be set via 'config.sh' or deployment script.
🔹 Required env vars: ENV_TRAIN_LP_S3_BUCKET, ENV_TRAIN_LP_SAGEMAKER_ROLE_ARN, etc.
"""

import sys
required_env_vars = [
    "ENV_TRAIN_LP_S3_BUCKET",
    "ENV_TRAIN_LP_SAGEMAKER_ROLE_ARN",
    "ENV_TRAIN_LP_AWS_REGION",
    "ENV_TRAIN_LP_AWS_ACCOUNT_ID",
    "ENV_TRAIN_LP_S3_PREFIX"
]
for var in required_env_vars:
    if not os.getenv(var):
        print(f"❌ ERROR: Required environment variable {var} is not set.")
        sys.exit(1)

import json
import os
import boto3
import logging

# Set up logging
logger = logging.getLogger()
logger.setLevel(logging.INFO)

def lambda_handler(event, context):
    """
    Lambda function that creates and starts a SageMaker training job.
    Accepts POST requests with optional hyperparameters.
    Environment variables are set by the deployment shell script.
    
    Example event:
    {
        "hyperparameters": {
            "learning_rate": "0.001",
            "batch_size": "16",
            "num_epochs": "10"
        },
        "job_name_suffix": "custom-run"  # Optional suffix for job name
    }
    """
    try:
        # Get environment variables
        env_vars = {
            "s3_bucket": os.environ.get("ENV_TRAIN_LP_S3_BUCKET"),
            "s3_prefix": os.environ.get("ENV_TRAIN_LP_S3_PREFIX"),
            "aws_region": os.environ.get("ENV_TRAIN_LP_AWS_REGION"),
            "sagemaker_role_arn": os.environ.get("ENV_TRAIN_LP_SAGEMAKER_ROLE_ARN")
        }
        
        # Validate environment variables
        for key, value in env_vars.items():
            if not value:
                error_msg = f"Missing required environment variable: ENV_TRAIN_LP_{key.upper()}"
                logger.error(error_msg)
                return {
                    "statusCode": 500,
                    "body": json.dumps({"error": error_msg})
                }
        
        # Extract parameters from the event
        job_name = "layout-parser-training"
        if event.get("job_name_suffix"):
            job_name = f"{job_name}-{event['job_name_suffix']}"
        
        # Set up S3 paths
        s3_bucket = env_vars["s3_bucket"]
        s3_prefix = env_vars["s3_prefix"]
        code_location = f"s3://{s3_bucket}/{s3_prefix}code/layoutparser_training.zip"
        output_path = f"s3://{s3_bucket}/{s3_prefix}output/"
        
        # Initialize SageMaker client
        sagemaker = boto3.client('sagemaker', region_name=env_vars["aws_region"])
        
        # Check if job with same name exists
        try:
            response = sagemaker.describe_training_job(TrainingJobName=job_name)
            # If exists, stop and delete it
            logger.info(f"Existing job found with status: {response['TrainingJobStatus']}. Stopping job.")
            try:
                sagemaker.stop_training_job(TrainingJobName=job_name)
                logger.info("Existing job stopped successfully.")
            except Exception as e:
                logger.warning(f"Could not stop job (may already be stopped): {str(e)}")
            
            # Wait for job to be stoppable
            waiter = sagemaker.get_waiter('training_job_completed_or_stopped')
            waiter.wait(TrainingJobName=job_name)
            
            # Delete the job
            sagemaker.delete_training_job(TrainingJobName=job_name)
            logger.info("Existing job deleted successfully.")
            
        except sagemaker.exceptions.ResourceNotFound:
            logger.info(f"No existing job found with name: {job_name}")
        
        # Set up hyperparameters
        hyperparameters = event.get("hyperparameters", {})
        
        # Add environment variables prefixed with ENV_TRAIN_LP_ to hyperparameters
        # This allows train.py to access these variables
        for key, value in os.environ.items():
            if key.startswith("ENV_TRAIN_LP_"):
                hyperparameters[key] = value
        
        # Set up training job configuration
        training_config = {
            "TrainingJobName": job_name,
            "RoleArn": env_vars["sagemaker_role_arn"],
            "AlgorithmSpecification": {
                "TrainingImage": f"763104351884.dkr.ecr.{env_vars['aws_region']}.amazonaws.com/pytorch-training:1.13.1-gpu-py39",
                "TrainingInputMode": "File"
            },
            "ResourceConfig": {
                "InstanceType": "ml.g4dn.xlarge",
                "InstanceCount": 1,
                "VolumeSizeInGB": 50
            },
            "InputDataConfig": [
                {
                    "ChannelName": "training",
                    "DataSource": {
                        "S3DataSource": {
                            "S3DataType": "S3Prefix",
                            "S3Uri": f"s3://{s3_bucket}/{s3_prefix}data/",
                            "S3DataDistributionType": "FullyReplicated"
                        }
                    }
                }
            ],
            "OutputDataConfig": {
                "S3OutputPath": output_path
            },
            "CodeLocation": code_location,
            "StoppingCondition": {
                "MaxRuntimeInSeconds": 86400,
                "MaxWaitTimeInSeconds": 129600
            },
            "EnableNetworkIsolation": False,
            "EnableManagedSpotTraining": True,
            "HyperParameters": hyperparameters
        }
        
        # Create training job
        response = sagemaker.create_training_job(**training_config)
        job_arn = response["TrainingJobArn"]
        
        return {
            "statusCode": 200,
            "body": json.dumps({
                "message": f"Training job '{job_name}' created successfully",
                "jobArn": job_arn,
                "jobName": job_name
            })
        }
        
    except Exception as e:
        error_message = f"Error creating training job: {str(e)}"
        logger.error(error_message)
        return {
            "statusCode": 500,
            "body": json.dumps({"error": error_message})
        }
