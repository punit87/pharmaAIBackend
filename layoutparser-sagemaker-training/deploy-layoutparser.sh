#!/bin/bash

echo "🔹 This script prepares S3 folder structure and deploys Lambda function for layoutparser training"
echo "🔹 It validates config.sh, environment variables, and AWS permissions"
echo "🔹 Requires: AWS CLI, Docker, jq, Bash >= 4"

# Exit on error and print commands
set -e

# Setup cleanup function
cleanup() {
    echo "🧹 Performing cleanup..."
    local original_dir=$(pwd)
    cd "$SCRIPT_DIR" || exit 1
    rm -rf ./layoutparser_training ./layoutparser_training.zip || true
    cd "$original_dir" || exit 1
    echo "Cleanup complete."
}

# Get script directory
SCRIPT_DIR="$( cd "$( dirname "${BASH_SOURCE[0]}" )" >/dev/null 2>&1 && pwd )"
trap cleanup EXIT

# Check prerequisites
for cmd in aws docker jq; do
    if ! command -v $cmd &> /dev/null; then
        echo "❌ ERROR: $cmd not installed."
        exit 1
    fi
done

if [ ! -f "${SCRIPT_DIR}/config.sh" ]; then
    echo "❌ ERROR: config.sh not found in script directory."
    exit 1
fi

# Source config.sh
echo "Loading configuration..."
source "${SCRIPT_DIR}/config.sh" || {
    echo "❌ ERROR: Failed to source config.sh"
    exit 1
}

# Verify environment variables
check_env_var() {
    if [ -z "${!1}" ]; then
        echo "❌ ERROR: Required environment variable $1 is not set in config.sh"
        return 1
    fi
}

# Verify all required environment variables
required_vars=(
    "ENV_TRAIN_LP_AWS_REGION"
    "ENV_TRAIN_LP_AWS_ACCOUNT_ID"
    "ENV_TRAIN_LP_SAGEMAKER_ROLE_ARN"
    "ENV_TRAIN_LP_S3_BUCKET"
    "ENV_TRAIN_LP_S3_PREFIX"
    "ENV_TRAIN_LP_LAMBDA_FUNCTION"
    "ENV_S3_PROFILE"
    "ENV_SAGEMAKER_PROFILE"
    "ENV_ECR_PROFILE"
    "ENV_LAMBDA_PROFILE"
    "ENV_TRAIN_LP_LAMBDA_ROLE_ARN"
)

for var in "${required_vars[@]}"; do
    if ! check_env_var "$var"; then
        exit 1
    fi
done

# Set variables with consistent naming
AWS_REGION=$ENV_TRAIN_LP_AWS_REGION
AWS_ACCOUNT_ID=$ENV_TRAIN_LP_AWS_ACCOUNT_ID
S3_BUCKET=$ENV_TRAIN_LP_S3_BUCKET
S3_PREFIX=$ENV_TRAIN_LP_S3_PREFIX
LAMBDA_FUNCTION_NAME=$ENV_TRAIN_LP_LAMBDA_FUNCTION
ECR_REPO_NAME="layout-parser-training-lambda"
ECR_REPO_URI="$AWS_ACCOUNT_ID.dkr.ecr.$AWS_REGION.amazonaws.com/$ECR_REPO_NAME"
LAMBDA_IMAGE_URI="$ECR_REPO_URI:latest"
S3_CODE_LOCATION="s3://$S3_BUCKET/${S3_PREFIX}code/layoutparser_training.zip"
LAMBDA_ROLE_ARN=$ENV_TRAIN_LP_LAMBDA_ROLE_ARN

# Verify AWS permissions (unchanged, as it's well implemented)
verify_permissions() {
    local profile=$1
    local service=$2
    local actions=("${@:3}")
    local resource=$4

    echo "🔍 Verifying $profile permissions for $service..."

    # Build IAM policy document for simulation
    local policy_document=$(jq -n \
        --arg actions "$(IFS=,; echo "${actions[*]}")" \
        --arg resource "$resource" \
        '{
            "Version": "2012-10-17",
            "Statement": [
                {
                    "Effect": "Allow",
                    "Action": ($actions | split(",")),
                    "Resource": ($resource | split(","))
                }
            ]
        }')

    # Simulate policy and capture output
    local result
    result=$(aws iam simulate-principal-policy \
        --policy-source-arn "arn:aws:iam::$AWS_ACCOUNT_ID:user/$profile" \
        --action-names "${actions[@]}" \
        --resource-arns "$resource" \
        --profile "$profile" \
        --region "$AWS_REGION" \
        2>&1)

    # Check for explicit denies first (most severe)
    if echo "$result" | jq -e '.EvaluationResults[] | select(.EvalDecision == "explicitDeny")' &>/dev/null; then
        echo "❌ ERROR: Profile $profile has EXPLICIT DENY permissions for:"
        echo "$result" | jq -r '.EvaluationResults[] | select(.EvalDecision == "explicitDeny") | .EvalActionName'
        return 1
    fi

    # Check for any non-allowed permissions (implicit denies or errors)
    if echo "$result" | jq -e '.EvaluationResults[] | select(.EvalDecision != "allowed")' &>/dev/null; then
        echo "❌ ERROR: Profile $profile is MISSING permissions for:"
        echo "$result" | jq -r '.EvaluationResults[] | select(.EvalDecision != "allowed") | .EvalActionName'
        
        # Provide additional debug info if available
        local debug_info=$(echo "$result" | jq -r '.EvaluationResults[] | select(.EvalDecision != "allowed") | {Action: .EvalActionName, Decision: .EvalDecision, Reason: .EvalDecisionReason}')
        echo "Debug information:"
        echo "$debug_info"
        
        return 1
    fi

    # Check for API errors
    if echo "$result" | jq -e '.Error' &>/dev/null; then
        echo "❌ ERROR: Failed to verify permissions for profile $profile:"
        echo "$result" | jq -r '.Error.Message'
        return 1
    fi

    echo "✅ Profile $profile has sufficient permissions for $service operations"
    return 0
}

# Verify permissions (same as original)
verify_permissions "$ENV_S3_PROFILE" "S3" \
    "s3:PutObject" "s3:GetObject" "s3:ListBucket" \
    "arn:aws:s3:::$S3_BUCKET,arn:aws:s3:::$S3_BUCKET/*" || exit 1

verify_permissions "$ENV_ECR_PROFILE" "ECR" \
    "ecr:CreateRepository" "ecr:DescribeRepositories" "ecr:BatchDeleteImage" "ecr:ListImages" "ecr:GetAuthorizationToken" "ecr:InitiateLayerUpload" "ecr:UploadLayerPart" "ecr:CompleteLayerUpload" "ecr:BatchCheckLayerAvailability" "ecr:PutImage" \
    "arn:aws:ecr:$AWS_REGION:$AWS_ACCOUNT_ID:repository/$ECR_REPO_NAME" || exit 1

verify_permissions "$ENV_LAMBDA_PROFILE" "Lambda" \
    "lambda:CreateFunction" "lambda:UpdateFunctionCode" "lambda:ListFunctions" "lambda:UpdateFunctionConfiguration" \
    "arn:aws:lambda:$AWS_REGION:$AWS_ACCOUNT_ID:function:$LAMBDA_FUNCTION_NAME" || exit 1

verify_permissions "$ENV_SAGEMAKER_PROFILE" "SageMaker" \
    "sagemaker:CreateTrainingJob" "sagemaker:DescribeTrainingJob" "sagemaker:StopTrainingJob" "sagemaker:DeleteTrainingJob" \
    "arn:aws:sagemaker:$AWS_REGION:$AWS_ACCOUNT_ID:training-job/layout-parser-training*" || exit 1

# Step 1: Package training code
echo "📦 Packaging training code..."
cd "$SCRIPT_DIR" || exit 1
rm -rf ./layoutparser_training ./layoutparser_training.zip
mkdir -p ./layoutparser_training
cp train.py requirements.txt ./layoutparser_training/
(cd ./layoutparser_training && zip -r ../layoutparser_training.zip .) || {
    echo "❌ Failed to create zip package (continuing...)"
}

# Step 2: Upload to S3
echo "📤 Uploading training package to S3..."
aws s3 cp ./layoutparser_training.zip "$S3_CODE_LOCATION" \
    --profile "$ENV_S3_PROFILE" \
    --region "$AWS_REGION" || {
    echo "❌ Failed to upload to S3 (continuing...)"
}

# Step 3: ECR Operations
echo "🐳 Managing ECR repository..."
if aws ecr describe-repositories --repository-names "$ECR_REPO_NAME" \
    --profile "$ENV_ECR_PROFILE" \
    --region "$AWS_REGION" >/dev/null 2>&1; then
    echo "ECR repository $ECR_REPO_NAME exists."
    
    # Check if there are images to delete
    IMAGE_IDS=$(aws ecr list-images --repository-name "$ECR_REPO_NAME" \
        --query 'imageIds[*]' \
        --output json \
        --profile "$ENV_ECR_PROFILE" \
        --region "$AWS_REGION")
    
    if [ -n "$IMAGE_IDS" ] && [ "$IMAGE_IDS" != "[]" ]; then
        echo "🗑️ Deleting existing ECR images..."
        aws ecr batch-delete-image \
            --repository-name "$ECR_REPO_NAME" \
            --image-ids "$IMAGE_IDS" \
            --profile "$ENV_ECR_PROFILE" \
            --region "$AWS_REGION" || {
            echo "❌ Failed to delete ECR images (continuing...)"
        }
    else
        echo "No images found in $ECR_REPO_NAME."
    fi
else
    echo "Creating ECR repository $ECR_REPO_NAME..."
    aws ecr create-repository --repository-name "$ECR_REPO_NAME" \
        --profile "$ENV_ECR_PROFILE" \
        --region "$AWS_REGION" || {
        echo "❌ Failed to create ECR repository"
        exit 1
    }
fi

# Build and push Docker image
echo "🏗️ Building and pushing Docker image..."
aws ecr get-login-password --profile "$ENV_ECR_PROFILE" --region "$AWS_REGION" | \
    docker login --username AWS --password-stdin "$AWS_ACCOUNT_ID.dkr.ecr.$AWS_REGION.amazonaws.com" || {
    echo "❌ Failed to login to ECR"
    exit 1
}

# Explicitly set build context directory
INVOKE_DIR="${SCRIPT_DIR}/invoke"
echo "Building from directory: $INVOKE_DIR"
ls -la "$INVOKE_DIR" || {
    echo "❌ Cannot list contents of invoke directory"
    exit 1
}

export DOCKER_BUILDKIT=1
docker buildx build \
  --platform linux/amd64 \
  --provenance=false \
  --output type=image,push=true \
  --tag "$LAMBDA_IMAGE_URI" \
  "$INVOKE_DIR" || {
    echo "❌ Docker build/push failed"
    echo "Debug info:"
    echo "- PWD: $(pwd)"
    echo "- Directory contents:"
    ls -la "$INVOKE_DIR"
    exit 1
}


cd "$SCRIPT_DIR" || exit 1

# Allow Lambda to pull the image
aws ecr set-repository-policy \
    --repository-name "$ECR_REPO_NAME" \
    --policy-text "{
        \"Version\": \"2012-10-17\",
        \"Statement\": [{
            \"Sid\": \"LambdaECRImageRetrievalPolicy\",
            \"Effect\": \"Allow\",
            \"Principal\": {\"Service\": \"lambda.amazonaws.com\"},
            \"Action\": [
                \"ecr:BatchGetImage\",
                \"ecr:GetDownloadUrlForLayer\"
            ],
            \"Condition\": {
                \"ArnLike\": {
                    \"aws:sourceArn\": \"arn:aws:lambda:$AWS_REGION:$AWS_ACCOUNT_ID:function:$LAMBDA_FUNCTION_NAME\"
                }
            }
        }]
    }" \
    --profile "$ENV_ECR_PROFILE" \
    --region "$AWS_REGION" || {
    echo "❌ Failed to set Lambda ECR permissions"
    exit 1
}

# Wait for policy to propagate
sleep 5

# Step 4: Lambda Operations
echo "λ Managing Lambda function..."
if aws lambda get-function --function-name "$LAMBDA_FUNCTION_NAME" \
    --profile "$ENV_LAMBDA_PROFILE" \
    --region "$AWS_REGION" &>/dev/null; then
    echo "🔄 Updating existing Lambda function"
    aws lambda update-function-code \
        --function-name "$LAMBDA_FUNCTION_NAME" \
        --image-uri "$LAMBDA_IMAGE_URI" \
        --profile "$ENV_LAMBDA_PROFILE" \
        --region "$AWS_REGION" || {
        echo "❌ Failed to update Lambda function code"
        exit 1
    }
    
    # Wait for update to complete
    aws lambda wait function-updated \
        --function-name "$LAMBDA_FUNCTION_NAME" \
        --profile "$ENV_LAMBDA_PROFILE" \
        --region "$AWS_REGION" || {
        echo "❌ Timed out waiting for Lambda update"
        exit 1
    }
else
    echo "🆕 Creating new Lambda function"
    aws lambda create-function \
        --function-name "$LAMBDA_FUNCTION_NAME" \
        --package-type Image \
        --code ImageUri="$LAMBDA_IMAGE_URI" \
        --role "$LAMBDA_ROLE_ARN" \
        --timeout 900 \
        --memory-size 1024 \
        --profile "$ENV_LAMBDA_PROFILE" \
        --region "$AWS_REGION" || {
        echo "❌ Failed to create Lambda function"
        exit 1
    }
    
    # Wait for function to be active
    aws lambda wait function-active \
        --function-name "$LAMBDA_FUNCTION_NAME" \
        --profile "$ENV_LAMBDA_PROFILE" \
        --region "$AWS_REGION" || {
        echo "❌ Timed out waiting for Lambda to be active"
        exit 1
    }
fi

# Step 5: Update Lambda configuration
echo "⚙️ Updating Lambda environment..."
aws lambda update-function-configuration \
    --function-name "$LAMBDA_FUNCTION_NAME" \
    --environment "Variables={ENV_TRAIN_LP_S3_BUCKET=$S3_BUCKET,ENV_TRAIN_LP_S3_PREFIX=$S3_PREFIX,ENV_TRAIN_LP_AWS_REGION=$AWS_REGION,ENV_TRAIN_LP_AWS_ACCOUNT_ID=$AWS_ACCOUNT_ID,ENV_TRAIN_LP_SAGEMAKER_ROLE_ARN=$ENV_TRAIN_LP_SAGEMAKER_ROLE_ARN,ENV_TRAIN_LP_CHECKPOINT_DIR=$ENV_TRAIN_LP_CHECKPOINT_DIR,ENV_TRAIN_LP_OUTPUT_DIR=$ENV_TRAIN_LP_OUTPUT_DIR,ENV_TRAIN_LP_PRETRAINED_DIR=$ENV_TRAIN_LP_PRETRAINED_DIR,ENV_TRAIN_LP_DEVICE=$ENV_TRAIN_LP_DEVICE,ENV_TRAIN_LP_LABEL_MAP='$ENV_TRAIN_LP_LABEL_MAP'}" \
    --profile "$ENV_LAMBDA_PROFILE" \
    --region "$AWS_REGION" || {
    echo "❌ Failed to update Lambda configuration (continuing...)"
}

echo "✅ Deployment complete!"
echo -e "\nTo invoke the Lambda function:"
echo "aws lambda invoke --function-name $LAMBDA_FUNCTION_NAME --profile $ENV_LAMBDA_PROFILE --payload '{}' response.json"