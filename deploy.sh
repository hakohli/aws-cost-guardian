#!/bin/bash
# Deploy AWS Cost Guardian to any customer account
# Run this from the PAYER (management) account for org-wide visibility
set -euo pipefail

usage() {
  cat <<EOF
Usage: ./deploy.sh --email <alert-email> [options]

Required:
  --email         Recipient email for alerts

Optional:
  --sender        SES verified sender email (default: same as --email)
  --days          Days before SP/RI expiry to alert (default: 30)
  --threshold     On-Demand monthly spend threshold \$ (default: 100)
  --schedule      Cron expression in UTC (default: "cron(0 9 * * ? *)")
  --region        AWS region (default: us-east-1)
  --disable       Deploy with schedule disabled
  --teardown      Delete the stack

Examples:
  ./deploy.sh --email team@company.com
  ./deploy.sh --email team@company.com --days 60 --threshold 500 --region us-west-2
  ./deploy.sh --email team@company.com --schedule "cron(0 14 ? * MON-FRI *)"
  ./deploy.sh --teardown --region us-east-1
EOF
  exit 1
}

EMAIL="" SENDER="" DAYS=30 THRESHOLD=100 REGION="us-east-1"
SCHEDULE="cron(0 9 * * ? *)" ENABLED="true" TEARDOWN=false

while [[ $# -gt 0 ]]; do
  case $1 in
    --email) EMAIL="$2"; shift 2;;
    --sender) SENDER="$2"; shift 2;;
    --days) DAYS="$2"; shift 2;;
    --threshold) THRESHOLD="$2"; shift 2;;
    --region) REGION="$2"; shift 2;;
    --schedule) SCHEDULE="$2"; shift 2;;
    --disable) ENABLED="false"; shift;;
    --teardown) TEARDOWN=true; shift;;
    *) echo "Unknown option: $1"; usage;;
  esac
done

if $TEARDOWN; then
  echo "Deleting aws-cost-guardian stack in $REGION..."
  aws cloudformation delete-stack --stack-name aws-cost-guardian --region "$REGION"
  echo "✅ Stack deletion initiated."
  exit 0
fi

[[ -z "$EMAIL" ]] && usage
[[ -z "$SENDER" ]] && SENDER="$EMAIL"

ACCOUNT=$(aws sts get-caller-identity --query Account --output text)

echo "╔══════════════════════════════════════════╗"
echo "║       AWS Cost Guardian — Deploy         ║"
echo "╠══════════════════════════════════════════╣"
echo "║  Account:    $ACCOUNT              ║"
echo "║  Region:     $REGION                    ║"
echo "║  Email:      $EMAIL"
echo "║  Sender:     $SENDER"
echo "║  Alert Days: $DAYS"
echo "║  OD Thresh:  \$$THRESHOLD"
echo "║  Schedule:   $SCHEDULE"
echo "║  Enabled:    $ENABLED"
echo "╚══════════════════════════════════════════╝"
echo ""

aws cloudformation deploy \
  --template-file "$(dirname "$0")/template.yaml" \
  --stack-name aws-cost-guardian \
  --parameter-overrides \
    AlertEmail="$EMAIL" \
    SenderEmail="$SENDER" \
    AlertDays="$DAYS" \
    OnDemandThreshold="$THRESHOLD" \
    ScheduleExpression="$SCHEDULE" \
    Enabled="$ENABLED" \
  --capabilities CAPABILITY_NAMED_IAM \
  --region "$REGION"

echo ""
echo "✅ Deployed to account $ACCOUNT ($REGION)"
echo ""
echo "Next steps:"
echo "  1. Confirm SNS subscription email sent to $EMAIL"
echo "  2. Test: aws lambda invoke --function-name cost-guardian --region $REGION /dev/stdout"
