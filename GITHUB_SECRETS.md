# GitHub Secrets Setup Guide

## Required Secrets

Set these secrets in: **GitHub Repository → Settings → Secrets and variables → Actions**

### 1. AWS Authentication
| Secret Name | Description | Example |
|------------|-------------|---------|
| `AWS_ACCOUNT_ID` | Your AWS Account ID | `864899869769` |
| `AWS_ROLE_ARN` | IAM Role for GitHub Actions | `arn:aws:iam::864899869769:role/GitHubActionsRole` |

### 2. Application Secrets
| Secret Name | Description | Where to Get |
|------------|-------------|--------------|
| `OPENAI_API_KEY` | OpenAI API Key | https://platform.openai.com/api-keys |
| `NEO4J_PASSWORD` | Neo4j Database Password | Neo4j AuraDB Console |

### 3. Optional Configuration
| Secret Name | Description | Default Value |
|------------|-------------|---------------|
| `NEO4J_URI` | Neo4j Connection URI | `neo4j+s://a16788ee.databases.neo4j.io` |
| `NEO4J_USERNAME` | Neo4j Username | `neo4j` |

---

## AWS IAM Role Setup

### Prerequisites
- AWS CLI installed and configured
- Admin access to AWS account

### Step 1: Create OIDC Provider
```bash
aws iam create-open-id-connect-provider \
  --url https://token.actions.githubusercontent.com \
  --client-id-list sts.amazonaws.com \
  --thumbprint-list 6938fd4d98bab03faadb97b34396831e3780aea1
```

### Step 2: Create Trust Policy
Create `github-actions-trust-policy.json`:
```json
{
  "Version": "2012-10-17",
  "Statement": [
    {
      "Effect": "Allow",
      "Principal": {
        "Federated": "arn:aws:iam::864899869769:oidc-provider/token.actions.githubusercontent.com"
      },
      "Action": "sts:AssumeRoleWithWebIdentity",
      "Condition": {
        "StringEquals": {
          "token.actions.githubusercontent.com:aud": "sts.amazonaws.com"
        },
        "StringLike": {
          "token.actions.githubusercontent.com:sub": "repo:punit87/pharmaAIBackend:*"
        }
      }
    }
  ]
}
```

⚠️ **Important**: Replace `864899869769` with your AWS Account ID

### Step 3: Create IAM Role
```bash
aws iam create-role \
  --role-name GitHubActionsRole \
  --assume-role-policy-document file://github-actions-trust-policy.json
```

### Step 4: Attach Required Policies
```bash
# ECS Access
aws iam attach-role-policy \
  --role-name GitHubActionsRole \
  --policy-arn arn:aws:iam::aws:policy/AmazonECS_FullAccess

# ECR Access
aws iam attach-role-policy \
  --role-name GitHubActionsRole \
  --policy-arn arn:aws:iam::aws:policy/AmazonEC2ContainerRegistryFullAccess

# CloudFormation Access
aws iam attach-role-policy \
  --role-name GitHubActionsRole \
  --policy-arn arn:aws:iam::aws:policy/CloudFormationFullAccess

# IAM Access (for creating roles/policies)
aws iam attach-role-policy \
  --role-name GitHubActionsRole \
  --policy-arn arn:aws:iam::aws:policy/IAMFullAccess

# S3 Access
aws iam attach-role-policy \
  --role-name GitHubActionsRole \
  --policy-arn arn:aws:iam::aws:policy/AmazonS3FullAccess

# API Gateway Access
aws iam attach-role-policy \
  --role-name GitHubActionsRole \
  --policy-arn arn:aws:iam::aws:policy/AmazonAPIGatewayAdministrator

# Lambda Access
aws iam attach-role-policy \
  --role-name GitHubActionsRole \
  --policy-arn arn:aws:iam::aws:policy/AWSLambda_FullAccess
```

### Step 5: Get Role ARN
```bash
aws iam get-role --role-name GitHubActionsRole --query 'Role.Arn' --output text
```

Copy the ARN and set it as `AWS_ROLE_ARN` secret in GitHub.

---

## Verification

After setting all secrets, trigger the GitHub Actions workflow by pushing to main:

```bash
git commit --allow-empty -m "Trigger deployment"
git push origin main
```

Check the Actions tab to see the deployment progress.

---

## Security Best Practices

1. **Never commit secrets** to the repository
2. **Rotate API keys** regularly
3. **Use least privilege** for IAM roles
4. **Monitor CloudWatch Logs** for suspicious activity
5. **Enable MFA** for AWS root account
6. **Review IAM policies** periodically

---

## Troubleshooting

### "Error: Unable to assume role"
- Verify OIDC provider exists
- Check trust policy repository name matches
- Ensure role has correct policies attached

### "Error: Access Denied"
- Verify all required policies are attached to IAM role
- Check AWS account ID is correct
- Ensure secrets are set correctly in GitHub

### "Error: Stack creation failed"
- Check CloudWatch Logs for detailed errors
- Verify parameter values are correct
- Ensure ECR repositories don't already exist

