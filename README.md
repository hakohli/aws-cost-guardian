# AWS Cost Guardian

Automated SP/RI monitoring with email alerts and interactive queries. Deploy to the **payer (management) account** for org-wide visibility.

## Features

| Feature | Description |
|---|---|
| SP Expiration Alerts | Alerts N days before any Savings Plan expires |
| RI Expiration Alerts | Scans EC2, RDS, OpenSearch, ElastiCache, Redshift RIs |
| Cross-Account Scanning | Scans linked accounts for RIs via StackSet role |
| Missing Coverage | Detects On-Demand spend with no SP/RI and shows recommendations |
| HTML Email Reports | Styled tables with color-coded badges via SES |
| Interactive Queries | Query cost data on demand via CLI |

## Architecture

```
Payer Account
├── EventBridge (daily) → Lambda → SES HTML Email
├── Lambda URL → Interactive queries
└── AssumeRole → Linked Account 1..N (RI scan)
```

## Quick Start

```bash
# 1. Deploy to payer account
./deploy.sh --email finance@company.com

# 2. Confirm SNS email subscription

# 3. Test
./query.sh summary
./query.sh "what's expiring?"
./query.sh "show recommendations"
./query.sh "on-demand spend"
```

## Cross-Account RI Scanning

To scan RIs in linked accounts, deploy the role via StackSet:

```bash
# Get your payer account ID
PAYER=$(aws sts get-caller-identity --query Account --output text)

# Deploy to each linked account (or use StackSets)
aws cloudformation deploy \
  --template-file linked-account-role.yaml \
  --stack-name cost-guardian-linked-role \
  --parameter-overrides PayerAccountId=$PAYER \
  --capabilities CAPABILITY_NAMED_IAM
```

## All Parameters

```bash
./deploy.sh \
  --email team@company.com \
  --sender noreply@company.com \
  --days 60 \
  --threshold 500 \
  --region us-west-2 \
  --schedule "cron(0 14 ? * MON-FRI *)" \
  --scan-linked true
```

| Flag | Default | Description |
|---|---|---|
| `--email` | (required) | Alert recipient |
| `--sender` | same as email | SES verified sender |
| `--days` | 30 | Days before expiry to alert |
| `--threshold` | 100 | On-Demand $ threshold |
| `--region` | us-east-1 | AWS region |
| `--schedule` | Daily 9AM UTC | EventBridge cron |
| `--scan-linked` | true | Scan linked accounts |
| `--teardown` | | Delete stack |

## Interactive Queries

```bash
./query.sh summary              # Overall status
./query.sh "what's expiring?"   # Expiring SP/RIs
./query.sh "recommendations"    # Purchase recommendations
./query.sh "on-demand spend"    # On-Demand breakdown
```

## Why Payer Account?

- Cost Explorer APIs return org-wide data only from management account
- Savings Plans are purchased at payer level
- Cross-account RI scanning requires AssumeRole from payer
- Single deployment covers entire organization

## Cost

~$0.01/month (1 Lambda/day + SES email).

## Tear Down

```bash
./deploy.sh --teardown
```

## License

MIT
