# Pharma RAG Infrastructure

This repository contains the infrastructure and application code for a serverless RAG (Retrieval-Augmented Generation) system built on AWS using ECS Fargate, Lambda, and Neo4j AuraDB.

## 🚀 Local Deployment

### Prerequisites
- AWS CLI configured with `pharma` profile
- Docker image built and pushed to ECR (via GitHub Actions)

### Setup Environment Variables
1. **Create a `.env` file with your configuration:**
   ```bash
   # OpenAI API Configuration
   OPENAI_API_KEY=sk-your-actual-openai-api-key
   
   # Neo4j Database Configuration
   NEO4J_URI=neo4j+s://your-actual-database-id.databases.neo4j.io
   NEO4J_USERNAME=neo4j
   NEO4J_PASSWORD=your-actual-neo4j-password
   
   # AWS Configuration (optional)
   AWS_PROFILE=pharma
   AWS_REGION=us-east-1
   S3_BUCKET=pharma-deployments-864899869769
   ```

### Deploy Infrastructure
```bash
# Deploy with environment variables from .env file
./deploy.sh
```

### What the script does:
1. ✅ Validates required environment variables
2. ✅ Checks ECR image exists
3. 📦 Packages Lambda functions and uploads to S3
4. 📦 Uploads CloudFormation templates to S3
5. 🚀 Deploys modular CloudFormation stack
6. 📊 Shows stack outputs and API endpoints
7. ⏱️ Provides timing information
8. 🧹 Cleans up temporary files

## Architecture Overview

```
┌─────────────────┐    ┌──────────────────┐    ┌─────────────────┐
│   API Gateway   │────│   Lambda APIs    │────│   ECS Fargate   │
│                 │    │                  │    │                 │
│ GET /presigned- │    │ • Presigned URL  │    │ • Docling       │
│ url             │    │ • RAG Query      │    │ • RAG-Anything  │
│ POST /rag-query │    │ • S3 Processor   │    │                 │
└─────────────────┘    └──────────────────┘    └─────────────────┘
         │                       │                       │
         │                       │                       │
         ▼                       ▼                       ▼
┌─────────────────┐    ┌──────────────────┐    ┌─────────────────┐
│      S3         │    │   CloudWatch     │    │   Neo4j AuraDB  │
│                 │    │                  │    │                 │
│ • Documents     │    │ • Logs           │    │ • Graph Storage │
│ • Processed     │    │ • Metrics        │    │ • Relationships │
│ • Queries       │    │                  │    │                 │
└─────────────────┘    └──────────────────┘    └─────────────────┘
```

## Components

### 1. Container Images
- **Docling**: Document processing with OCR and content extraction
- **RAG-Anything**: RAG query processing and response generation

### 2. AWS Services
- **ECS Fargate**: Containerized document processing and RAG queries
- **Lambda**: API endpoints and S3 event processing
- **API Gateway**: REST API endpoints
- **S3**: Document storage and processed data
- **Neo4j AuraDB**: Graph database for relationships and context

### 3. API Endpoints
- `GET /presigned-url`: Generate presigned S3 URL for document upload
- `POST /rag-query`: Process RAG queries and return responses

## Prerequisites

1. **AWS Account** with appropriate permissions
2. **Neo4j AuraDB** instance (provided connection details)
3. **OpenAI API Key** for LLM integration
4. **GitHub Secrets** configured:
   - `AWS_ACCESS_KEY_ID`
   - `AWS_SECRET_ACCESS_KEY`
   - `AWS_ACCOUNT_ID`
   - `OPENAI_API_KEY`
   - `NEO4J_URI`
   - `NEO4J_USERNAME`
   - `NEO4J_PASSWORD`

## Deployment

### 1. Manual Deployment (Images Already Built)

Since the container images are already built and available in ECR, you can deploy the infrastructure directly:

```bash
# Deploy infrastructure
aws cloudformation deploy \
  --template-file infrastructure/ecs-infrastructure.yml \
  --stack-name pharma-rag-infrastructure-dev \
  --capabilities CAPABILITY_IAM CAPABILITY_NAMED_IAM \
  --parameter-overrides \
    Environment=dev \
    DoclingImageUri=YOUR_ACCOUNT_ID.dkr.ecr.us-east-1.amazonaws.com/pharma-docling:latest \
    RaganythingImageUri=YOUR_ACCOUNT_ID.dkr.ecr.us-east-1.amazonaws.com/pharma-raganything:latest \
    OpenAIApiKey=your_openai_key \
    Neo4jUri=neo4j+s://a16788ee.databases.neo4j.io \
    Neo4jUsername=neo4j \
    Neo4jPassword=your_neo4j_password \
  --region us-east-1
```

### 2. GitHub Actions Deployment

The deployment workflow will automatically:
1. Deploy CloudFormation infrastructure
2. Update Lambda function code
3. Configure API Gateway endpoints

Trigger deployment by:
- Pushing changes to `main` branch
- Manual workflow dispatch with environment selection

## Usage

### 1. Upload Document

```bash
# Get presigned URL
curl -X GET https://your-api-gateway-url/dev/presigned-url

# Upload document using presigned URL
curl -X PUT -T your-document.pdf "presigned-url-from-response"
```

### 2. Query Documents

```bash
curl -X POST https://your-api-gateway-url/dev/rag-query \
  -H "Content-Type: application/json" \
  -d '{"query": "What is the main topic of the document?"}'
```

## Configuration

### Environment Variables

**ECS Tasks:**
- `S3_BUCKET`: S3 bucket for document storage
- `NEO4J_URI`: Neo4j connection URI
- `NEO4J_USERNAME`: Neo4j username
- `NEO4J_PASSWORD`: Neo4j password
- `OPENAI_API_KEY`: OpenAI API key

**Lambda Functions:**
- `ECS_CLUSTER`: ECS cluster name
- `DOCLING_TASK_DEFINITION`: Docling task definition ARN
- `RAGANYTHING_TASK_DEFINITION`: RAG-Anything task definition ARN
- `SUBNETS`: Comma-separated subnet IDs
- `SECURITY_GROUP`: Security group ID

### ECS Task Configuration

**Docling Task:**
- CPU: 2048 (2 vCPU)
- Memory: 4096 MB (4 GB)
- Network: Fargate with VPC

**RAG-Anything Task:**
- CPU: 1024 (1 vCPU)
- Memory: 2048 MB (2 GB)
- Network: Fargate with VPC

## Monitoring

### CloudWatch Logs
- ECS tasks: `/ecs/pharma-docling-{environment}` and `/ecs/pharma-raganything-{environment}`
- Lambda functions: `/aws/lambda/pharma-{function-name}-{environment}`

### CloudWatch Metrics
- ECS task metrics (CPU, Memory, Network)
- Lambda metrics (Duration, Errors, Invocations)
- API Gateway metrics (Request count, Latency, Error rate)

## Troubleshooting

### Common Issues

1. **ECS Task Fails to Start**
   - Check security group rules
   - Verify subnet configuration
   - Check ECR image permissions

2. **Lambda Timeout**
   - Increase timeout in CloudFormation template
   - Check ECS task completion time

3. **Neo4j Connection Issues**
   - Verify connection URI and credentials
   - Check network connectivity from ECS tasks

4. **S3 Access Denied**
   - Verify IAM role permissions
   - Check bucket policy

### Debugging

```bash
# Check ECS task logs
aws logs tail /ecs/pharma-docling-dev --follow

# Check Lambda logs
aws logs tail /aws/lambda/pharma-presigned-url-dev --follow

# Check ECS task status
aws ecs describe-tasks --cluster pharma-cluster-dev --tasks task-arn
```

## Cost Optimization

- Use Fargate Spot for non-critical workloads
- Configure S3 lifecycle policies for old versions
- Set appropriate CloudWatch log retention
- Use appropriate ECS task sizes based on workload

## Security

- All S3 buckets have public access blocked
- ECS tasks run in private subnets
- Lambda functions have minimal required permissions
- Neo4j credentials stored as environment variables
- API Gateway has CORS configured

## Scaling

- ECS tasks scale automatically based on demand
- Lambda functions scale automatically
- S3 provides unlimited storage
- Neo4j AuraDB scales automatically

## Support

For issues or questions:
1. Check CloudWatch logs for error details
2. Verify all environment variables are set correctly
3. Ensure all AWS services have proper permissions
4. Check Neo4j AuraDB connectivity and credentials
