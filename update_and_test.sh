#!/bin/bash

set -e

echo "🚀 Starting ECS update and test process..."

# Configuration
CLUSTER_NAME="${CLUSTER_NAME:-pharma-rag-cluster}"
SERVICE_NAME="${SERVICE_NAME:-pharma-raganything-async-service}"
REGION="${AWS_REGION:-us-east-1}"

echo ""
echo "=========================================="
echo "Step 1: Force ECS Service Update"
echo "=========================================="
echo ""

echo "Updating service: $SERVICE_NAME in cluster: $CLUSTER_NAME"

aws ecs update-service \
    --cluster $CLUSTER_NAME \
    --service $SERVICE_NAME \
    --force-new-deployment \
    --region $REGION

echo ""
echo "✅ Service update initiated"
echo "Waiting 30 seconds before checking status..."
sleep 30

echo ""
echo "=========================================="
echo "Step 2: Check Service Status"
echo "=========================================="
echo ""

aws ecs describe-services \
    --cluster $CLUSTER_NAME \
    --services $SERVICE_NAME \
    --region $REGION \
    --query 'services[0].deployments[]' \
    --output table

echo ""
echo "=========================================="
echo "Step 3: Get ECS Task to Clear EFS"
echo "=========================================="
echo ""

TASK_ARN=$(aws ecs list-tasks --cluster $CLUSTER_NAME --query 'taskArns[0]' --output text --region $REGION)

if [ -z "$TASK_ARN" ] || [ "$TASK_ARN" == "None" ]; then
    echo "❌ No tasks found. Waiting 30 more seconds..."
    sleep 30
    TASK_ARN=$(aws ecs list-tasks --cluster $CLUSTER_NAME --query 'taskArns[0]' --output text --region $REGION)
fi

if [ -z "$TASK_ARN" ] || [ "$TASK_ARN" == "None" ]; then
    echo "❌ Still no tasks found. Please check ECS console."
    exit 1
fi

echo "Task ARN: $TASK_ARN"

echo ""
echo "=========================================="
echo "Step 4: Clear EFS Data"
echo "=========================================="
echo ""

echo "To clear EFS data, you need to SSH into the task:"
echo ""
echo "1. Enable ECS Exec on your task:"
echo "   aws ecs update-service --cluster $CLUSTER_NAME --service $SERVICE_NAME --enable-execute-command"
echo ""
echo "2. Connect to the task:"
echo "   aws ecs execute-command --cluster $CLUSTER_NAME --task $TASK_ARN --container pharma-raganything-async --interactive --command \"/bin/bash\""
echo ""
echo "3. Once connected, run:"
echo "   rm -rf /rag-output/*"
echo ""
echo "OR manually clear EFS using the mount point"

read -p "Press Enter when EFS is cleared, or type 'skip' to continue without clearing: " response
if [ "$response" == "skip" ]; then
    echo "Skipping EFS clearing..."
else
    echo "Assuming EFS will be cleared manually"
fi

echo ""
echo "=========================================="
echo "Step 5: Test Deployment"
echo "=========================================="
echo ""

echo "Now test your endpoints:"
echo ""
echo "1. Get presigned URL:"
echo "   curl -X POST \$API_URL/presigned-url -H 'Content-Type: application/json' -d '{\"filename\": \"1.pdf\"}'"
echo ""
echo "2. Upload file to S3 using presigned URL"
echo ""
echo "3. Trigger processing:"
echo "   curl -X POST \$API_URL/process -H 'Content-Type: application/json' -d '{\"bucket\": \"...\", \"key\": \"...\"}'"
echo ""
echo "4. Wait 30-60 seconds for processing"
echo ""
echo "5. Query:"
echo "   curl -X POST \$API_URL/query -H 'Content-Type: application/json' -d '{\"query\": \"What is the document about?\", \"mode\": \"hybrid\"}'"
echo ""

echo "✅ Update script completed!"
echo ""
echo "Check CloudWatch logs for detailed processing info:"
echo "aws logs tail /aws/ecs/pharma-raganything-async --follow"

