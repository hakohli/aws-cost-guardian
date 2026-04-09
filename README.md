# AWS Cost Guardian

Automated monitoring for AWS Savings Plans and Reserved Instances — expiration alerts, missing coverage detection, and purchase recommendations delivered as styled HTML emails.

**Deploy to the payer (management) account** for org-wide visibility across all linked accounts.

## What It Does

| Check | Alert When |
|---|---|
| SP Expiration | Savings Plan expires within N days |
| RI Expiration | Any RI (EC2, RDS, OpenSearch, ElastiCache, Redshift) expires within N days |
| Missing Coverage | On-Demand spend exceeds threshold with no active SP/RI |
| Recommendations | Includes AWS purchase recommendations with estimated savings |

## Architecture

```
EventBridge (configurable cron)
       │
       ▼
Lambda (cost-guardian)
       │
       ├── Savings Plans API
       ├── EC2/RDS/OpenSearch/ElastiCache/Redshift RI APIs
       ├── Cost Explorer (On-Demand spend + recommendations)
       │
       ▼
SES → Styled HTML email with tables
```

## Deploy

```bash
# Basic — defaults to 30 days, $100 threshold, 9AM UTC daily
./deploy.sh --email team@company.com

# Custom thresholds
./deploy.sh --email team@company.com --days 60 --threshold 500

# Different region
./deploy.sh --email team@company.com --region us-west-2

# Weekdays only at 2PM UTC
./deploy.sh --email team@company.com --schedule "cron(0 14 ? * MON-FRI *)"

# Tear down
./deploy.sh --teardown --region us-east-1
```

## Parameters

| Parameter | Default | Description |
|---|---|---|
| `--email` | (required) | Recipient email |
| `--sender` | same as email | SES verified sender |
| `--days` | `30` | Days before expiry to alert |
| `--threshold` | `100` | On-Demand monthly $ threshold |
| `--schedule` | `cron(0 9 * * ? *)` | EventBridge schedule (UTC) |
| `--region` | `us-east-1` | AWS region |
| `--disable` | | Deploy with schedule off |

## Why Payer Account?

- Cost Explorer APIs return org-wide data only from the management account
- Savings Plans are purchased at the payer level
- RIs purchased with org sharing are visible from the payer
- Linked accounts only see their own RIs

## Prerequisites

- SES verified sender email (or SES out of sandbox for production)
- IAM permissions to deploy CloudFormation with IAM resources

## Cost

~$0.01/month — 1 Lambda invocation/day + SES email.

## License

MIT
