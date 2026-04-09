# AWS Cost Guardian

Automated monitoring for AWS Savings Plans, Reserved Instances, and cost optimization recommendations. Deploys as a single CloudFormation stack — one Lambda, one daily trigger, one SNS topic.

## What It Does

- **Expiration Alerts**: Notifies you 30 days before any SP or RI expires (EC2, RDS, OpenSearch, ElastiCache, Redshift)
- **Missing Coverage Alerts**: Detects if you have On-Demand spend with no SP/RI coverage and includes purchase recommendations
- **Daily Summary**: Runs every morning at 9 AM UTC with a consolidated report

## Architecture

```
EventBridge (daily cron 9AM UTC)
       │
       ▼
Lambda (cost-guardian)
       │
       ├── Check Savings Plans expiry
       ├── Check EC2/RDS/OpenSearch/ElastiCache/Redshift RIs
       ├── Check for missing SP/RI coverage
       ├── Pull AWS recommendations
       │
       ▼
  SNS → Email / Slack / PagerDuty
```

## Deploy

```bash
aws cloudformation deploy \
  --template-file template.yaml \
  --stack-name aws-cost-guardian \
  --parameter-overrides AlertEmail=you@example.com AlertDays=30 \
  --capabilities CAPABILITY_NAMED_IAM \
  --region us-east-1
```

**Confirm the SNS subscription email** after deployment.

## Parameters

| Parameter | Default | Description |
|---|---|---|
| `AlertEmail` | (required) | Email for alerts |
| `AlertDays` | `30` | Days before expiry to start alerting |
| `OnDemandThreshold` | `100` | Monthly On-Demand spend ($) that triggers "no SP/RI" alert |

## Cost

~$0.01/month (1 Lambda invocation per day, SNS email delivery).

## Tear Down

```bash
aws cloudformation delete-stack --stack-name aws-cost-guardian --region us-east-1
```

## License

MIT
