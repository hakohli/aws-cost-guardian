#!/bin/bash
# Deploy AWS Cost Guardian to payer account
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

Interactive queries:
  ./query.sh summary
  ./query.sh "what's expiring?"
  ./query.sh "show recommendations"
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

echo "╔══════════════════════════════════════════════╗"
echo "║         AWS Cost Guardian — Deploy           ║"
echo "╠══════════════════════════════════════════════╣"
printf "║  Account:       %-28s║\n" "$ACCOUNT"
printf "║  Region:        %-28s║\n" "$REGION"
printf "║  Email:         %-28s║\n" "$EMAIL"
printf "║  Alert Days:    %-28s║\n" "$DAYS"
printf "║  OD Threshold:  \$%-27s║\n" "$THRESHOLD"
printf "║  Scan Linked:   %-28s║\n" "$SCAN"
printf "║  Schedule:      %-28s║\n" "$SCHEDULE"
echo "╚══════════════════════════════════════════════╝"
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
    ScanLinkedAccounts="$SCAN" \
  --capabilities CAPABILITY_NAMED_IAM \
  --region "$REGION"

echo ""
echo "✅ Deployed to $ACCOUNT ($REGION)"
echo ""
echo "Next steps:"
echo "  1. Confirm SNS email subscription"
echo "  2. Test alert:  aws lambda invoke --function-name cost-guardian --region $REGION --cli-binary-format raw-in-base64-out --payload '{}' /dev/stdout"
echo "  3. Test query:  ./query.sh summary"
if [[ "$SCAN" == "true" ]]; then
  echo "  4. Deploy linked role: aws cloudformation deploy --template-file linked-account-role.yaml --stack-name cost-guardian-linked-role --parameter-overrides PayerAccountId=$ACCOUNT --capabilities CAPABILITY_NAMED_IAM"
fi
