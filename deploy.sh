#!/bin/bash
set -euo pipefail

usage() {
  cat <<EOF
Usage: ./deploy.sh --email <email> [options]

Required:
  --email           Recipient email

Optional:
  --sender          SES verified sender (default: same as --email)
  --days            Days before expiry to alert (default: 30)
  --threshold       On-Demand monthly \$ threshold (default: 100)
  --schedule        Cron expression UTC (default: "cron(0 9 * * ? *)")
  --region          AWS region (default: us-east-1)
  --scan-linked     Scan linked accounts for RIs (default: true)
  --teardown        Delete the stack
EOF
  exit 1
}

EMAIL="" SENDER="" DAYS=30 THRESHOLD=100 REGION="us-east-1"
SCHEDULE="cron(0 9 * * ? *)" SCAN="true" TEARDOWN=false

while [[ $# -gt 0 ]]; do
  case $1 in
    --email) EMAIL="$2"; shift 2;;
    --sender) SENDER="$2"; shift 2;;
    --days) DAYS="$2"; shift 2;;
    --threshold) THRESHOLD="$2"; shift 2;;
    --region) REGION="$2"; shift 2;;
    --schedule) SCHEDULE="$2"; shift 2;;
    --scan-linked) SCAN="$2"; shift 2;;
    --teardown) TEARDOWN=true; shift;;
    *) echo "Unknown: $1"; usage;;
  esac
done

if $TEARDOWN; then
  echo "Deleting aws-cost-guardian in $REGION..."
  aws cloudformation delete-stack --stack-name aws-cost-guardian --region "$REGION"
  echo "✅ Done."; exit 0
fi

[[ -z "$EMAIL" ]] && usage
[[ -z "$SENDER" ]] && SENDER="$EMAIL"
ACCOUNT=$(aws sts get-caller-identity --query Account --output text)
BUCKET="cost-guardian-data-${ACCOUNT}"
SCRIPT_DIR="$(cd "$(dirname "$0")" && pwd)"

echo "╔══════════════════════════════════════════════╗"
echo "║         AWS Cost Guardian — Deploy           ║"
echo "╠══════════════════════════════════════════════╣"
printf "║  Account:       %-28s║\n" "$ACCOUNT"
printf "║  Region:        %-28s║\n" "$REGION"
printf "║  Email:         %-28s║\n" "$EMAIL"
printf "║  Alert Days:    %-28s║\n" "$DAYS"
printf "║  OD Threshold:  \$%-27s║\n" "$THRESHOLD"
printf "║  Scan Linked:   %-28s║\n" "$SCAN"
echo "╚══════════════════════════════════════════════╝"
echo ""

# Package Lambda
echo "📦 Packaging Lambda..."
cd "$SCRIPT_DIR/lambda"
zip -q /tmp/cost-guardian.zip index.py
cd "$SCRIPT_DIR"

# Deploy (first pass creates bucket, Lambda uses inline placeholder)
echo "🚀 Deploying stack..."
aws cloudformation deploy \
  --template-file "$SCRIPT_DIR/template.yaml" \
  --stack-name aws-cost-guardian \
  --parameter-overrides \
    AlertEmail="$EMAIL" \
    SenderEmail="$SENDER" \
    AlertDays="$DAYS" \
    OnDemandThreshold="$THRESHOLD" \
    ScheduleExpression="$SCHEDULE" \
    ScanLinkedAccounts="$SCAN" \
  --capabilities CAPABILITY_NAMED_IAM \
  --region "$REGION"

# Get the CFN-generated bucket name
BUCKET=$(aws cloudformation describe-stacks --stack-name aws-cost-guardian --region "$REGION" \
  --query 'Stacks[0].Outputs[?OutputKey==`DataBucket`].OutputValue' --output text)

# Upload Lambda code to the bucket and update function
aws s3 cp /tmp/cost-guardian.zip "s3://${BUCKET}/lambda/cost-guardian.zip" --region "$REGION"
aws lambda update-function-code \
  --function-name cost-guardian \
  --s3-bucket "$BUCKET" \
  --s3-key lambda/cost-guardian.zip \
  --region "$REGION" > /dev/null

echo ""
echo "✅ Deployed to $ACCOUNT ($REGION)"
echo ""
echo "Next steps:"
echo "  1. Confirm SNS email subscription"
echo "  2. Test:  aws lambda invoke --function-name cost-guardian --region $REGION --cli-binary-format raw-in-base64-out --payload '{}' /dev/stdout"
echo "  3. Query: ./query.sh summary"
echo "  4. Set up QuickSight Chat Agent: see quicksight-agent-setup.md"
