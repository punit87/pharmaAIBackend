#!/bin/bash

# Pharma RAG Infrastructure Deployment Script
# This script deploys the CloudFormation stack locally

set -e  # Exit on any error

echo "🚀 [DEPLOY] Starting local CloudFormation deployment at $(date)"
DEPLOY_START=$(date +%s.%3N)

# Configuration
STACK_NAME="pharma-rag-infrastructure-dev"
TEMPLATE_FILE="infrastructure/ecs-infrastructure.yml"
AWS_REGION="us-east-1"
AWS_PROFILE="pharma"

# Get AWS Account ID
AWS_ACCOUNT_ID=$(aws sts get-caller-identity --query Account --output text --profile $AWS_PROFILE --region $AWS_REGION)
echo "📋 [DEPLOY] AWS Account ID: $AWS_ACCOUNT_ID"

# Set image URI
RAGANYTHING_IMAGE_URI="$AWS_ACCOUNT_ID.dkr.ecr.$AWS_REGION.amazonaws.com/pharma-raganything-dev:latest"
echo "📋 [DEPLOY] RAG-Anything Image URI: $RAGANYTHING_IMAGE_URI"

# Check if ECR image exists
echo "🔍 [DEPLOY] Checking if ECR image exists..."
if aws ecr describe-images --repository-name pharma-raganything-dev --image-ids imageTag=latest --region $AWS_REGION --profile $AWS_PROFILE >/dev/null 2>&1; then
    echo "✅ [DEPLOY] ECR image exists: $RAGANYTHING_IMAGE_URI"
else
    echo "❌ [DEPLOY] ECR image not found: $RAGANYTHING_IMAGE_URI"
    echo "❌ [DEPLOY] Please run the build workflow first to create the Docker image"
    exit 1
fi

# Deploy CloudFormation stack
echo "🚀 [DEPLOY] Starting CloudFormation deployment..."
CF_START=$(date +%s.%3N)

aws cloudformation deploy \
  --template-file "$TEMPLATE_FILE" \
  --stack-name "$STACK_NAME" \
  --capabilities CAPABILITY_IAM CAPABILITY_NAMED_IAM \
  --parameter-overrides \
    Environment="dev" \
    RaganythingImageUri="$RAGANYTHING_IMAGE_URI" \
    OpenAIApiKey="$OPENAI_API_KEY" \
    Neo4jUri="$NEO4J_URI" \
    Neo4jUsername="$NEO4J_USERNAME" \
    Neo4jPassword="$NEO4J_PASSWORD" \
  --region "$AWS_REGION" \
  --profile "$AWS_PROFILE"

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
  echo "📋 [DEPLOY] Server: MVP Mode with ECS Task execution"
fi

echo "✅ [DEPLOY] Deployment completed successfully!"
