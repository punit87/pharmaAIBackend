# Pharma RAG Infrastructure - Modular CloudFormation

This directory contains a modular CloudFormation infrastructure setup for the Pharma RAG system. The infrastructure is broken down into logical, reusable components for better maintainability and organization.

## Structure

```
infrastructure/
├── main.yml              # Main orchestrator template
├── network.yml           # VPC, subnets, security groups
├── storage.yml           # S3 buckets, EFS
├── ecs.yml              # ECS cluster, task definitions
├── lambda.yml           # All Lambda functions
├── api-gateway.yml      # API Gateway and integrations
└── README.md            # This file
```

## Templates Overview

### 1. `main.yml` - Main Orchestrator
- **Purpose**: Orchestrates all other stacks using nested stacks
- **Dependencies**: All other templates
- **Outputs**: Main API Gateway URL and other key resources

### 2. `network.yml` - Network Infrastructure
- **Purpose**: VPC, subnets, security groups, routing
- **Resources**:
  - VPC with public/private subnets across 2 AZs
  - Internet Gateway and NAT Gateway
  - Security groups for ECS and Lambda
  - Route tables and associations
- **Outputs**: VPC ID, subnet IDs, security group IDs

### 3. `storage.yml` - Storage Infrastructure
- **Purpose**: S3 buckets and EFS file systems
- **Resources**:
  - S3 bucket for document storage
  - S3 bucket policies
  - EFS file system for RAG outputs
- **Outputs**: S3 bucket name and ARN

### 4. `ecs.yml` - ECS Infrastructure
- **Purpose**: ECS cluster, task definitions, and related resources
- **Resources**:
  - ECS Fargate cluster
  - Task definitions for RAG-Anything
  - IAM roles for ECS tasks
  - EFS mount targets
- **Dependencies**: Network stack (for VPC/subnets)
- **Outputs**: ECS cluster name, task definition ARN

### 5. `lambda.yml` - Lambda Functions
- **Purpose**: All Lambda functions and their configurations
- **Resources**:
  - Presigned URL function
  - Health check function
  - RAG query function
  - Document processor function
  - Multimodal query function
  - IAM roles and policies
  - Lambda layers
- **Dependencies**: Network, ECS, and Storage stacks
- **Outputs**: Lambda function ARNs

### 6. `api-gateway.yml` - API Gateway
- **Purpose**: API Gateway and Lambda integrations
- **Resources**:
  - REST API Gateway
  - API resources and methods
  - Lambda permissions
  - API deployment
- **Dependencies**: Lambda stack
- **Outputs**: API Gateway URL

## Deployment

### Prerequisites
1. AWS CLI configured with appropriate permissions
2. Environment variables set (see `.env` file)
3. ECR image built and pushed
4. S3 bucket for CloudFormation templates

### Deploy All Modules
```bash
./deploy-modular.sh
```

### Deploy Individual Modules
You can also deploy individual modules for development/testing:

```bash
# Deploy network first
aws cloudformation deploy \
  --template-file infrastructure/network.yml \
  --stack-name pharma-network-dev \
  --capabilities CAPABILITY_IAM \
  --parameter-overrides Environment=dev

# Deploy storage
aws cloudformation deploy \
  --template-file infrastructure/storage.yml \
  --stack-name pharma-storage-dev \
  --capabilities CAPABILITY_IAM \
  --parameter-overrides Environment=dev

# And so on...
```

## Benefits of Modular Approach

### 1. **Maintainability**
- Each template focuses on a specific concern
- Easier to understand and modify individual components
- Reduced risk of breaking unrelated resources

### 2. **Reusability**
- Templates can be reused across different environments
- Easy to create variations (e.g., different VPC configurations)
- Components can be shared between projects

### 3. **Development Workflow**
- Developers can work on specific modules independently
- Faster deployment times for individual components
- Easier to test changes in isolation

### 4. **Troubleshooting**
- Easier to identify which module has issues
- Smaller, focused logs and outputs
- Clearer dependency relationships

### 5. **Team Collaboration**
- Different teams can own different modules
- Clear separation of concerns
- Reduced merge conflicts

## Cross-Stack References

The modules use CloudFormation exports and imports to share resources:

```yaml
# In network.yml - Export
Outputs:
  VPCId:
    Value: !Ref VPC
    Export:
      Name: !Sub '${AWS::StackName}-VPC'

# In ecs.yml - Import
Parameters:
  VPCId:
    Type: String
    Description: VPC ID from network stack
```

## Environment Management

Each template supports multiple environments through parameters:

```yaml
Parameters:
  Environment:
    Type: String
    Default: dev
    AllowedValues: [dev, dev-1, dev-2, staging, prod]
```

## Best Practices

1. **Always deploy in dependency order**: Network → Storage → ECS → Lambda → API Gateway
2. **Use consistent naming**: All resources include environment prefix
3. **Export important outputs**: Make resources available to other stacks
4. **Validate templates**: Use `aws cloudformation validate-template` before deployment
5. **Monitor stack events**: Check CloudFormation console for deployment issues

## Troubleshooting

### Common Issues

1. **Circular Dependencies**: Ensure proper dependency order
2. **Missing Exports**: Check that required outputs are exported
3. **Parameter Mismatches**: Verify parameter names and types match
4. **Resource Limits**: Check AWS service limits

### Debugging Commands

```bash
# Check stack status
aws cloudformation describe-stacks --stack-name pharma-rag-infrastructure-dev

# View stack events
aws cloudformation describe-stack-events --stack-name pharma-rag-infrastructure-dev

# Validate template
aws cloudformation validate-template --template-body file://infrastructure/network.yml
```

## Future Enhancements

1. **CI/CD Integration**: Automated deployment pipelines
2. **Environment Promotion**: Staging → Production workflows
3. **Monitoring**: CloudWatch dashboards and alarms
4. **Security**: Additional security groups and policies
5. **Backup**: Automated backup strategies
