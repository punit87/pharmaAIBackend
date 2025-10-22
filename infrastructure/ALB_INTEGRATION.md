# ALB Integration for Pharma RAG System

This document describes the Application Load Balancer (ALB) integration that provides a robust connection between Lambda functions and ECS tasks.

## Architecture Overview

The system now uses an ALB to route traffic from Lambda functions to ECS tasks instead of direct IP connections. This provides several benefits:

- **Better Reliability**: ALB handles health checks and automatically routes traffic to healthy tasks
- **Load Balancing**: Distributes traffic across multiple ECS tasks if needed
- **Simplified Connection**: Lambda functions connect to a stable ALB endpoint instead of dynamic IP addresses
- **Better Monitoring**: ALB provides metrics and logs for traffic analysis

## Components

### 1. ALB Infrastructure (`infrastructure/alb.yml`)
- **Application Load Balancer**: Internet-facing ALB in public subnets
- **Target Group**: Routes traffic to ECS tasks on port 8000
- **Listeners**: HTTP (port 80) and HTTPS (port 443) listeners
- **Health Checks**: Monitors ECS tasks via `/health` endpoint

### 2. Updated ECS Service (`infrastructure/ecs.yml`)
- **Target Group Registration**: ECS service automatically registers tasks with ALB target group
- **Health Check Grace Period**: 60 seconds for tasks to become healthy
- **Load Balancer Integration**: Tasks are registered with ALB when they start

### 3. Updated Lambda Functions
- **rag_query_alb.py**: Uses ALB endpoint instead of direct IP
- **document_processor_alb.py**: Processes documents via ALB
- **rag_query_multimodal_alb.py**: Handles multimodal queries via ALB

### 4. Network Security (`infrastructure/network.yml`)
- **ALB Security Group**: Allows inbound HTTP/HTTPS traffic
- **ECS Security Group**: Allows inbound traffic from ALB on port 8000
- **Lambda Security Group**: Allows outbound traffic to ALB

## Key Changes

### Lambda Function Updates
The Lambda functions now:
1. Start ECS tasks as before
2. Wait for tasks to be running
3. Wait additional 30 seconds for ALB health checks to pass
4. Make requests to ALB endpoint instead of direct task IP
5. Stop tasks after processing to save costs

### ALB Endpoint Usage
```python
# Old approach (direct IP)
server_url = f"http://{private_ip}:8000"

# New approach (ALB endpoint)
alb_endpoint = os.environ['ALB_ENDPOINT']
server_url = f"http://{alb_endpoint}"
```

## Deployment

### 1. Package ALB Lambda Functions
```bash
./package_alb_lambdas.sh
```

### 2. Upload Lambda Packages to S3
```bash
aws s3 cp lambda-packages/rag_query_alb.zip s3://your-bucket/lambda-packages/
aws s3 cp lambda-packages/document_processor_alb.zip s3://your-bucket/lambda-packages/
aws s3 cp lambda-packages/rag_query_multimodal_alb.zip s3://your-bucket/lambda-packages/
```

### 3. Deploy Infrastructure
```bash
aws cloudformation deploy \
  --template-file infrastructure/main.yml \
  --stack-name pharma-rag-alb \
  --parameter-overrides \
    Environment=dev \
    RaganythingImageUri=your-image-uri \
    OpenAIApiKey=your-api-key \
    Neo4jUri=your-neo4j-uri \
    Neo4jUsername=your-username \
    Neo4jPassword=your-password \
    S3Bucket=your-s3-bucket
```

## Benefits

### Reliability
- ALB automatically handles unhealthy tasks
- Health checks ensure only healthy tasks receive traffic
- Automatic failover if tasks become unhealthy

### Performance
- ALB provides connection pooling
- Better handling of concurrent requests
- Reduced cold start impact

### Monitoring
- ALB access logs for traffic analysis
- CloudWatch metrics for ALB performance
- Better visibility into request patterns

### Cost Optimization
- Tasks are still stopped after processing to save costs
- ALB provides efficient connection management
- Reduced Lambda execution time due to better connection handling

## Configuration

### ALB Health Checks
- **Path**: `/health`
- **Interval**: 30 seconds
- **Timeout**: 5 seconds
- **Healthy Threshold**: 2 consecutive successes
- **Unhealthy Threshold**: 3 consecutive failures
- **Grace Period**: 60 seconds

### Lambda Timeout
- **Query Functions**: 300 seconds (5 minutes)
- **Document Processor**: 300 seconds (5 minutes)
- **Health Check Wait**: 30 seconds additional wait for ALB

## Troubleshooting

### Common Issues

1. **ALB Health Check Failures**
   - Ensure ECS tasks are responding on `/health` endpoint
   - Check security group rules allow ALB to reach ECS tasks
   - Verify tasks are running on port 8000

2. **Lambda Timeout Issues**
   - Increase Lambda timeout if needed
   - Check ALB health check grace period
   - Verify ECS tasks start within expected time

3. **Connection Issues**
   - Verify ALB endpoint is accessible from Lambda
   - Check VPC configuration and subnet routing
   - Ensure security groups allow traffic flow

### Monitoring
- Check ALB target group health in AWS Console
- Monitor CloudWatch logs for Lambda execution
- Review ALB access logs for request patterns
- Monitor ECS service events for task lifecycle

## Migration from Direct IP

The system maintains backward compatibility. To migrate:

1. Deploy the new ALB-enabled infrastructure
2. Update Lambda functions to use ALB endpoint
3. Test functionality with ALB
4. Remove old direct IP Lambda functions if desired

The ALB approach provides a more robust and scalable solution for connecting Lambda functions to ECS tasks.
