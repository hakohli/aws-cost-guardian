#!/bin/bash
# Deploy AWS Cost Guardian to any account
set -euo pipefail

EMAIL="${1:?Usage: ./deploy.sh <alert-email> [alert-days] [od-threshold] [region]}"
ALERT_DAYS="${2:-30}"
OD_THRESHOLD="${3:-100}"
REGION="${4:-us-east-1}"

echo "Deploying AWS Cost Guardian..."
echo "  Email: $EMAIL"
echo "  Alert Days: $ALERT_DAYS"
echo "  On-Demand Threshold: \$$OD_THRESHOLD"
echo "  Region: $REGION"

aws cloudformation deploy \
  --template-file template.yaml \
  --stack-name aws-cost-guardian \
  --parameter-overrides \
    AlertEmail="$EMAIL" \
    AlertDays="$ALERT_DAYS" \
    OnDemandThreshold="$OD_THRESHOLD" \
  --capabilities CAPABILITY_NAMED_IAM \
  --region "$REGION"

echo ""
echo "✅ Deployed! Check your email ($EMAIL) to confirm the SNS subscription."
echo ""
echo "Test it now:"
echo "  aws lambda invoke --function-name cost-guardian --region $REGION /dev/stdout"
