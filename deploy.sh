#!/bin/bash

# Pharma RAG Infrastructure Deployment Script
# This script deploys the complete CloudFormation infrastructure with proper Lambda packaging

set -e  # Exit on any error

echo "🚀 [DEPLOY] Starting CloudFormation deployment at $(date)"
DEPLOY_START=$(date +%s.%3N)

# Load environment variables from .env file if it exists
if [ -f .env ]; then
    echo "📋 [DEPLOY] Loading environment variables from .env file..."
    export $(grep -v '^#' .env | xargs)
else
    echo "⚠️  [DEPLOY] No .env file found. Using environment variables from shell."
    echo "💡 [DEPLOY] Create a .env file with your configuration for easier management."
fi

# Configuration
STACK_NAME="${STACK_NAME:-pharma-rag-infrastructure-dev}"
MAIN_TEMPLATE="infrastructure/main.yml"
AWS_REGION="${AWS_REGION:-us-east-1}"
AWS_PROFILE="${AWS_PROFILE:-pharma}"
S3_BUCKET="${AWS_DEPLOYMENT_BUCKET:-pharma-deployments-864899869769}"

# Validate required environment variables
echo "🔍 [DEPLOY] Validating required environment variables..."
REQUIRED_VARS=("OPENAI_API_KEY" "NEO4J_URI" "NEO4J_USERNAME" "NEO4J_PASSWORD")
MISSING_VARS=()

for var in "${REQUIRED_VARS[@]}"; do
    if [ -z "${!var}" ]; then
        MISSING_VARS+=("$var")
    fi
done

if [ ${#MISSING_VARS[@]} -ne 0 ]; then
    echo "❌ [DEPLOY] Missing required environment variables:"
    for var in "${MISSING_VARS[@]}"; do
        echo "   - $var"
    done
    echo "💡 [DEPLOY] Please set these variables in your .env file or shell environment."
    exit 1
fi

echo "✅ [DEPLOY] All required environment variables are set."

# Get AWS Account ID
AWS_ACCOUNT_ID=$(aws sts get-caller-identity --query Account --output text --profile $AWS_PROFILE --region $AWS_REGION)
echo "📋 [DEPLOY] AWS Account ID: $AWS_ACCOUNT_ID"

# Set image URI
RAGANYTHING_IMAGE_URI="$AWS_ACCOUNT_ID.dkr.ecr.$AWS_REGION.amazonaws.com/pharma-raganything-dev:latest"
echo "📋 [DEPLOY] RAG-Anything Image URI: $RAGANYTHING_IMAGE_URI"

# Validate ECR image exists
echo "🔍 [DEPLOY] Checking if ECR image exists..."
if aws ecr describe-images --repository-name pharma-raganything-dev --image-ids imageTag=latest --region $AWS_REGION --profile $AWS_PROFILE >/dev/null 2>&1; then
    echo "✅ [DEPLOY] ECR image exists: $RAGANYTHING_IMAGE_URI"
else
    echo "❌ [DEPLOY] ECR image not found: $RAGANYTHING_IMAGE_URI"
    echo "❌ [DEPLOY] Please run the build workflow first to create the Docker image"
    exit 1
fi

# Package Lambda functions
echo "📦 [DEPLOY] Packaging Lambda functions with dependencies..."
LAMBDA_PACKAGE_DIR="lambda-packages"
mkdir -p "$LAMBDA_PACKAGE_DIR"

# Install Python packages into a local lib directory
INSTALL_LIBS_DIR="lambda-local-libs"
echo "📦 [DEPLOY] Installing Lambda dependencies to $INSTALL_LIBS_DIR..."
mkdir -p "$INSTALL_LIBS_DIR"
pip install -r lambda/requirements.txt -t "$INSTALL_LIBS_DIR" --no-deps || pip3 install -r lambda/requirements.txt -t "$INSTALL_LIBS_DIR" --no-deps

# Lambda functions that need external dependencies
LAMBDAS_WITH_DEPS=("document_processor" "document_deleter" "rag_query" "rag_query_multimodal" "websocket_message")

# Package each Lambda function
for lambda_file in lambda/*.py; do
    if [ -f "$lambda_file" ]; then
        lambda_name=$(basename "$lambda_file" .py)
        echo "📦 [DEPLOY] Packaging $lambda_name..."
        
        # Create a temporary directory for this Lambda
        temp_dir=$(mktemp -d)
        cp "$lambda_file" "$temp_dir/"
        
        # Check if this Lambda needs external dependencies
        NEEDS_DEPS=false
        for deps_lambda in "${LAMBDAS_WITH_DEPS[@]}"; do
            if [ "$lambda_name" = "$deps_lambda" ]; then
                NEEDS_DEPS=true
                break
            fi
        done
        
        if [ "$NEEDS_DEPS" = true ]; then
            echo "📦 [DEPLOY] Including external dependencies for $lambda_name..."
            cp -r "$INSTALL_LIBS_DIR"/* "$temp_dir/" 2>/dev/null || true
        fi
        
        # Create zip file in the temp directory
        cd "$temp_dir"
        zip -r "${lambda_name}.zip" . -x "*.pyc" -x "__pycache__/*" -x "*.dist-info/*"
        cd - > /dev/null
        
        # Move zip file to package directory
        mv "$temp_dir/${lambda_name}.zip" "$LAMBDA_PACKAGE_DIR/"
        
        # Upload to S3
        aws s3 cp "$LAMBDA_PACKAGE_DIR/${lambda_name}.zip" "s3://$S3_BUCKET/lambda-packages/${lambda_name}.zip" --profile "$AWS_PROFILE" --region "$AWS_REGION"
        echo "✅ [DEPLOY] Uploaded $lambda_name.zip to S3"
        
        # Clean up temp directory
        rm -rf "$temp_dir"
    fi
done

# Clean up local libs directory
rm -rf "$INSTALL_LIBS_DIR"

# Upload CloudFormation templates to S3
echo "📦 [DEPLOY] Uploading CloudFormation templates to S3..."
TEMPLATES=("infrastructure/network.yml" "infrastructure/storage.yml" "infrastructure/ecs.yml" "infrastructure/lambda.yml" "infrastructure/api-gateway.yml" "infrastructure/websocket.yml")

for template in "${TEMPLATES[@]}"; do
    if [ -f "$template" ]; then
        template_name=$(basename "$template")
        aws s3 cp "$template" "s3://$S3_BUCKET/cloudformation-templates/$template_name" --profile "$AWS_PROFILE" --region "$AWS_REGION"
        echo "✅ [DEPLOY] Uploaded $template_name"
    else
        echo "❌ [DEPLOY] Template not found: $template"
        exit 1
    fi
done

echo "🚀 [DEPLOY] Starting CloudFormation deployment..."
CF_START=$(date +%s.%3N)

# Set environment from .env file
ENVIRONMENT="${ENVIRONMENT:-dev}"

aws cloudformation deploy \
  --template-file "$MAIN_TEMPLATE" \
  --stack-name "$STACK_NAME" \
  --capabilities CAPABILITY_IAM CAPABILITY_NAMED_IAM \
  --disable-rollback \
  --parameter-overrides \
    Environment="${ENVIRONMENT}" \
    RaganythingImageUri="$RAGANYTHING_IMAGE_URI" \
    OpenAIApiKey="$OPENAI_API_KEY" \
    Neo4jUri="$NEO4J_URI" \
    Neo4jUsername="$NEO4J_USERNAME" \
    Neo4jPassword="$NEO4J_PASSWORD" \
    S3Bucket="$S3_BUCKET" \
  --region "$AWS_REGION" \
  --profile "$AWS_PROFILE" \
  --s3-bucket "$S3_BUCKET"

CF_END=$(date +%s.%3N)
CF_DURATION=$(echo "$CF_END - $CF_START" | bc)
echo "✅ [DEPLOY] CloudFormation deployment completed in ${CF_DURATION}s"

# Get stack outputs
echo "📊 [DEPLOY] Retrieving stack outputs..."
OUTPUTS_START=$(date +%s.%3N)
echo "Stack Outputs:"
aws cloudformation describe-stacks \
  --stack-name "$STACK_NAME" \
  --query 'Stacks[0].Outputs' \
  --output table \
  --region "$AWS_REGION" \
  --profile "$AWS_PROFILE"
OUTPUTS_END=$(date +%s.%3N)
OUTPUTS_DURATION=$(echo "$OUTPUTS_END - $OUTPUTS_START" | bc)
echo "✅ [DEPLOY] Stack outputs retrieved in ${OUTPUTS_DURATION}s"

# Get API Gateway URL
echo "🔗 [DEPLOY] Getting API Gateway URL..."
API_START=$(date +%s.%3N)
API_URL=$(aws cloudformation describe-stacks \
  --stack-name "$STACK_NAME" \
  --query "Stacks[0].Outputs[?OutputKey=='ApiGatewayUrl'].OutputValue" \
  --output text \
  --region "$AWS_REGION" \
  --profile "$AWS_PROFILE" 2>/dev/null || echo "")
API_END=$(date +%s.%3N)
API_DURATION=$(echo "$API_END - $API_START" | bc)
echo "✅ [DEPLOY] API Gateway URL retrieved in ${API_DURATION}s"

TOTAL_END=$(date +%s.%3N)
TOTAL_DURATION=$(echo "$TOTAL_END - $DEPLOY_START" | bc)
echo "🎉 [DEPLOY] Total deployment time: ${TOTAL_DURATION}s"

if [ ! -z "$API_URL" ]; then
  echo "🌐 [DEPLOY] API Gateway URL: $API_URL"
  echo "🧪 [DEPLOY] Available endpoints:"
  echo "  GET  $API_URL/presigned-url          # Get S3 presigned URL for upload"
  echo "  POST $API_URL/rag-query              # Standard RAG query"
  echo "  POST $API_URL/rag-query-multimodal   # Multimodal RAG query"
  echo "  GET  $API_URL/health                 # Health check"
  echo "📋 [DEPLOY] Query modes: hybrid, local, global, naive"
  echo "📋 [DEPLOY] Parsers: docling"
  echo "📋 [DEPLOY] Server: ECS Task execution with auto-scaling"
fi

# Clean up local packages
echo "🧹 [DEPLOY] Cleaning up local packages..."
rm -rf "$LAMBDA_PACKAGE_DIR"

echo "✅ [DEPLOY] CloudFormation deployment completed successfully!"
