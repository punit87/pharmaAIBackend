#!/bin/bash

# Pharma RAG Infrastructure Deployment Script
# This script deploys the CloudFormation infrastructure for the Pharma RAG system

set -e

# Configuration
STACK_NAME="pharma-rag-infrastructure"
ENVIRONMENT="dev"
AWS_REGION="us-east-1"
TEMPLATE_FILE="infrastructure/ecs-infrastructure.yml"

# Colors for output
RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
NC='\033[0m' # No Color

# Function to print colored output
print_status() {
    echo -e "${GREEN}[INFO]${NC} $1"
}

print_warning() {
    echo -e "${YELLOW}[WARNING]${NC} $1"
}

print_error() {
    echo -e "${RED}[ERROR]${NC} $1"
}

# Check if AWS CLI is installed
if ! command -v aws &> /dev/null; then
    print_error "AWS CLI is not installed. Please install it first."
    exit 1
fi

# Check if template file exists
if [ ! -f "$TEMPLATE_FILE" ]; then
    print_error "CloudFormation template not found: $TEMPLATE_FILE"
    exit 1
fi

# Get AWS Account ID
AWS_ACCOUNT_ID=$(aws sts get-caller-identity --query Account --output text)
if [ -z "$AWS_ACCOUNT_ID" ]; then
    print_error "Failed to get AWS Account ID. Please check your AWS credentials."
    exit 1
fi

print_status "AWS Account ID: $AWS_ACCOUNT_ID"

# Set ECR image URIs
ECR_REGISTRY="$AWS_ACCOUNT_ID.dkr.ecr.$AWS_REGION.amazonaws.com"
DOCLING_IMAGE_URI="$ECR_REGISTRY/pharma-docling:latest"
RAGANYTHING_IMAGE_URI="$ECR_REGISTRY/pharma-raganything:latest"

print_status "Docling Image URI: $DOCLING_IMAGE_URI"
print_status "RAG-Anything Image URI: $RAGANYTHING_IMAGE_URI"

# Prompt for required parameters
echo ""
print_warning "Please provide the following required parameters:"

read -p "OpenAI API Key: " OPENAI_API_KEY
if [ -z "$OPENAI_API_KEY" ]; then
    print_error "OpenAI API Key is required"
    exit 1
fi

read -p "Neo4j Password: " NEO4J_PASSWORD
if [ -z "$NEO4J_PASSWORD" ]; then
    print_error "Neo4j Password is required"
    exit 1
fi

# Set default values
NEO4J_URI="neo4j+s://a16788ee.databases.neo4j.io"
NEO4J_USERNAME="neo4j"

print_status "Deploying CloudFormation stack: $STACK_NAME-$ENVIRONMENT"
print_status "Region: $AWS_REGION"
print_status "Template: $TEMPLATE_FILE"

# Deploy CloudFormation stack
aws cloudformation deploy \
    --template-file "$TEMPLATE_FILE" \
    --stack-name "$STACK_NAME-$ENVIRONMENT" \
    --capabilities CAPABILITY_IAM CAPABILITY_NAMED_IAM \
    --parameter-overrides \
        Environment="$ENVIRONMENT" \
        DoclingImageUri="$DOCLING_IMAGE_URI" \
        RaganythingImageUri="$RAGANYTHING_IMAGE_URI" \
        OpenAIApiKey="$OPENAI_API_KEY" \
        Neo4jUri="$NEO4J_URI" \
        Neo4jUsername="$NEO4J_USERNAME" \
        Neo4jPassword="$NEO4J_PASSWORD" \
    --region "$AWS_REGION"

if [ $? -eq 0 ]; then
    print_status "CloudFormation stack deployed successfully!"
    
    # Get stack outputs
    echo ""
    print_status "Stack Outputs:"
    aws cloudformation describe-stacks \
        --stack-name "$STACK_NAME-$ENVIRONMENT" \
        --query 'Stacks[0].Outputs' \
        --output table \
        --region "$AWS_REGION"
    
    # Get API Gateway URL
    API_URL=$(aws cloudformation describe-stacks \
        --stack-name "$STACK_NAME-$ENVIRONMENT" \
        --query 'Stacks[0].Outputs[?OutputKey==`ApiGatewayUrl`].OutputValue' \
        --output text \
        --region "$AWS_REGION")
    
    if [ ! -z "$API_URL" ]; then
        echo ""
        print_status "API Gateway URL: $API_URL"
        echo ""
        print_status "Test endpoints:"
        echo "  GET  $API_URL/presigned-url"
        echo "  POST $API_URL/rag-query"
        echo ""
        print_status "Example usage:"
        echo "  # Get presigned URL"
        echo "  curl -X GET $API_URL/presigned-url"
        echo ""
        echo "  # Query documents"
        echo "  curl -X POST $API_URL/rag-query \\"
        echo "    -H 'Content-Type: application/json' \\"
        echo "    -d '{\"query\": \"What is the main topic?\"}'"
    fi
    
else
    print_error "CloudFormation deployment failed!"
    exit 1
fi

print_status "Deployment completed successfully!"
