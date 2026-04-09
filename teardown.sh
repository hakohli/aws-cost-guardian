#!/bin/bash
# Remove AWS Cost Guardian stack
set -euo pipefail
REGION="${1:-us-east-1}"
echo "Deleting aws-cost-guardian stack in $REGION..."
aws cloudformation delete-stack --stack-name aws-cost-guardian --region "$REGION"
echo "✅ Stack deletion initiated."
