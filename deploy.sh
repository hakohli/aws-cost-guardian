#!/bin/bash
# Deploy AWS Cost Guardian to any account
set -euo pipefail

EMAIL="${1:?Usage: ./deploy.sh <alert-email> [sender-email] [alert-days] [od-threshold] [region]}"
SENDER="${2:-$EMAIL}"
ALERT_DAYS="${3:-30}"
OD_THRESHOLD="${4:-100}"
REGION="${5:-us-east-1}"

echo "Deploying AWS Cost Guardian..."
echo "  Alert Email:  $EMAIL"
echo "  Sender Email: $SENDER"
echo "  Alert Days:   $ALERT_DAYS"
echo "  OD Threshold: \$$OD_THRESHOLD"
echo "  Region:       $REGION"

aws cloudformation deploy \
  --template-file template.yaml \
  --stack-name aws-cost-guardian \
  --parameter-overrides \
    AlertEmail="$EMAIL" \
    SenderEmail="$SENDER" \
    AlertDays="$ALERT_DAYS" \
    OnDemandThreshold="$OD_THRESHOLD" \
  --capabilities CAPABILITY_NAMED_IAM \
  --region "$REGION"

echo ""
echo "✅ Deployed!"
echo ""
echo "Test it now:"
echo "  aws lambda invoke --function-name cost-guardian --region $REGION /dev/stdout"
