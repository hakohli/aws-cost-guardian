# AWS Cost Guardian

Automated SP/RI monitoring with email alerts, CLI queries, and an **Amazon Quick custom chat agent** for conversational cost optimization. Deploy to the payer account for org-wide visibility.

## Features

| Feature | Description |
|---|---|
| Email Alerts | Daily HTML email with expiring SPs/RIs, On-Demand spend, recommendations |
| Cross-Account Scanning | Scans linked accounts for RIs via StackSet role |
| CLI Queries | `./query.sh summary` for on-demand data |
| QuickSight Dashboard | Pre-built visuals for SP/RI coverage and spend trends |
| **Quick Chat Agent** | Conversational AI — ask "what's expiring?" in natural language |
| Historical Trends | Daily snapshots in S3 → Athena → trend analysis over time |

## Architecture

```
Lambda (daily)
  ├── SES HTML Email → ops/finance team
  ├── S3 CSV Export → Athena → QuickSight
  │                              ├── Dashboard (visuals)
  │                              └── Custom Chat Agent (conversational)
  ├── Cross-account AssumeRole → linked account RIs
  └── CLI query interface
```

## Quick Start

```bash
# 1. Deploy
./deploy.sh --email finance@company.com

# 2. Confirm SNS email

# 3. Test
./query.sh summary

# 4. Set up QuickSight Chat Agent
# See quicksight-agent-setup.md
```

## QuickSight Chat Agent

After deployment, create a custom chat agent in Amazon Quick that lets your team ask:

```
"Which savings plans expire this month?"
"Show me On-Demand spend by service"
"What are the top recommendations?"
"Which accounts have no RI coverage?"
"Compare spend trend over the last 30 days"
```

See [quicksight-agent-setup.md](quicksight-agent-setup.md) for step-by-step instructions.

## All Parameters

| Flag | Default | Description |
|---|---|---|
| `--email` | (required) | Alert recipient |
| `--sender` | same as email | SES verified sender |
| `--days` | 30 | Days before expiry to alert |
| `--threshold` | 100 | On-Demand $ threshold |
| `--region` | us-east-1 | AWS region |
| `--schedule` | Daily 9AM UTC | EventBridge cron |
| `--scan-linked` | true | Scan linked accounts |

## What Gets Deployed

| Resource | Purpose |
|---|---|
| Lambda | Core logic — collects data, sends email, writes to S3 |
| S3 Bucket | Daily CSV snapshots (365-day retention) |
| Glue Database + Tables | Athena-queryable tables for QuickSight |
| Athena Workgroup | Query engine |
| EventBridge Rule | Daily trigger |
| SNS Topic | Email subscription |
| IAM Role | Lambda permissions |

## Cross-Account RI Scanning

```bash
PAYER=$(aws sts get-caller-identity --query Account --output text)
aws cloudformation deploy \
  --template-file linked-account-role.yaml \
  --stack-name cost-guardian-linked-role \
  --parameter-overrides PayerAccountId=$PAYER \
  --capabilities CAPABILITY_NAMED_IAM
```

## Cost

~$0.05/month (Lambda + S3 + Athena + SES).

## License

MIT
