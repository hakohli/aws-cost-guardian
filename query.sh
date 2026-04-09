#!/bin/bash
# Interactive query against Cost Guardian
# Usage: ./query.sh <question>
set -euo pipefail

QUERY="${1:-summary}"
REGION="${AWS_REGION:-us-east-1}"

echo "🔍 Querying Cost Guardian: \"$QUERY\""
echo ""

aws lambda invoke \
  --function-name cost-guardian \
  --region "$REGION" \
  --cli-binary-format raw-in-base64-out \
  --payload "{\"action\": \"query\", \"query\": \"$QUERY\"}" \
  /tmp/cg-query-result.json > /dev/null 2>&1

python3 -m json.tool /tmp/cg-query-result.json
