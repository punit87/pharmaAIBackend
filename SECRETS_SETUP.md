# GitHub Secrets Setup

This document explains how to set up the required GitHub secrets for the Pharma RAG infrastructure deployment. The deployment is fully automated through GitHub Actions.

## Required Secrets

Configure the following secrets in your GitHub repository:

### 1. AWS Secrets
- `AWS_ACCOUNT_ID`: Your AWS Account ID (e.g., `864899869769`)
- `AWS_ROLE_ARN`: ARN of the IAM role for GitHub Actions (e.g., `arn:aws:iam::864899869769:role/GitHubActionsRole`)

### 2. API Keys
- `OPENAI_API_KEY`: Your OpenAI API key (e.g., `sk-proj-...`)
- `NEO4J_PASSWORD`: Your Neo4j database password

### 3. Neo4j Configuration (Optional - defaults provided)
- `NEO4J_URI`: Neo4j connection URI (default: `neo4j+s://a16788ee.databases.neo4j.io`)
- `NEO4J_USERNAME`: Neo4j username (default: `neo4j`)

## How to Set Up Secrets

1. Go to your GitHub repository
2. Click on **Settings** tab
3. In the left sidebar, click on **Secrets and variables** → **Actions**
4. Click **New repository secret**
5. Add each secret with the exact name and value

## Automated Deployment

The deployment is fully automated through GitHub Actions:

1. **Build**: Docker images are built for both Docling and RAG-Anything containers
2. **Push**: Images are pushed to Amazon ECR
3. **Deploy**: CloudFormation stack is deployed with the new images
4. **Output**: API Gateway URL and endpoints are displayed

No manual intervention required - just push to the `main` branch!

## IAM Role Setup

Create an IAM role for GitHub Actions with the following trust policy:

```json
{
  "Version": "2012-10-17",
  "Statement": [
    {
      "Effect": "Allow",
      "Principal": {
        "Federated": "arn:aws:iam::YOUR_ACCOUNT_ID:oidc-provider/token.actions.githubusercontent.com"
      },
      "Action": "sts:AssumeRoleWithWebIdentity",
      "Condition": {
        "StringEquals": {
          "token.actions.githubusercontent.com:aud": "sts.amazonaws.com"
        },
        "StringLike": {
          "token.actions.githubusercontent.com:sub": "repo:YOUR_USERNAME/pharmaAIBackend:*"
        }
      }
    }
  ]
}
```

Attach the following policies to the role:
- `AmazonECS_FullAccess`
- `AmazonEC2ContainerRegistryFullAccess`
- `CloudFormationFullAccess`
- `IAMFullAccess`
- `AmazonS3FullAccess`
- `AmazonAPIGatewayAdministrator`

## Security Notes

- Never commit sensitive information to the repository
- Use GitHub secrets for all sensitive data
- Rotate API keys regularly
- Use least privilege principle for IAM roles
