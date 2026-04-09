# AWS Cost Guardian

Automated SP/RI monitoring with email alerts, CLI queries, and an **Amazon Quick custom chat agent** for conversational cost optimization. Deploy to the payer (management) account for org-wide visibility.

## Why Cost Guardian? How Is It Different from Native AWS Services?

AWS provides individual cost management tools — Budgets, Cost Anomaly Detection, Cost Explorer — but they operate as separate, disconnected services that require customers to actively monitor multiple consoles. Cost Guardian brings everything together into a single, proactive solution.

| Capability | AWS Native | Cost Guardian |
|---|---|---|
| **SP/RI expiry alerts** | Budgets alerts on coverage *drop* (after the fact) | Alerts **30 days before** expiry with exact plan ID, commitment, and date |
| **Missing coverage detection** | No native service alerts when running 100% On-Demand | Detects zero SP/RI coverage and alerts with dollar breakdown + recommendations |
| **Consolidated view** | SP console + RI console + Cost Explorer + Budgets (4 separate places) | One HTML email + one QuickSight Chat Agent — everything in one place |
| **Non-technical access** | Requires AWS Console access and navigation | Amazon Quick Chat Agent — anyone asks "what's expiring?" in plain English |
| **Cross-account RI visibility** | RI describe APIs are account-scoped | Scans all linked accounts via cross-account roles, complete org-wide picture |
| **Purchase recommendations** | Cost Explorer has them, but you must go look | Included in every alert email alongside expiry and spend data |
| **Historical trends** | Cost Explorer: 12-month lookback, no SP/RI timeline | Daily S3 snapshots → Athena → QuickSight trend analysis over time |
| **Deployment** | Manual setup across multiple services | One CloudFormation stack, all parameters configurable, zero maintenance |

### What Native AWS Services Cover (and Where They Stop)

- **AWS Budgets** — Can set RI/SP coverage budgets, but only alerts when coverage *drops below a threshold*. It doesn't tell you "SP abc123 expires in 22 days at $5.50/hr." No specifics, no proactive timeline.

- **AWS Cost Anomaly Detection** — Excellent for unexpected cost spikes, but has no awareness of SP/RI expiration. It won't alert you that your $10K/month Savings Plan expires next week.

- **AWS Cost Explorer Recommendations** — Has SP and RI purchase recommendations, but they sit passively in the console. No one gets an email saying "you could save $3,200/mo if you buy this Compute SP."

- **AWS Cost & Usage Report (CUR)** — Raw billing data. Powerful but requires building your own Athena queries, dashboards, and alerting on top of it.

- **Amazon Q in QuickSight** — Can answer questions about data, but you need to build the dataset and configure the topic first. Cost Guardian provides the pre-built data pipeline and chat agent instructions.

### The Gap Cost Guardian Fills

```
Native AWS:  Tools exist, but scattered across 5+ consoles.
             Reactive, not proactive. Technical users only.

Cost Guardian: One deployment → proactive alerts + chat agent + dashboards.
               Finance team asks "what's expiring?" — gets an answer.
               Ops team gets an email before anything expires.
               Leadership sees a dashboard without touching the AWS Console.
```

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
# 1. Deploy to payer account
./deploy.sh --email finance@company.com

# 2. Confirm SNS email

# 3. Test
./query.sh summary

# 4. Set up QuickSight Chat Agent
# See quicksight-agent-setup.md
```

Or deploy via AWS Console: CloudFormation → Create Stack → Upload `template.yaml` → fill in parameters.

## CloudFormation Parameters

| Parameter | Default | Description |
|---|---|---|
| Alert Email | (required) | Who receives cost alerts |
| Sender Email | (required) | SES verified sender address |
| Expiry Alert Window | 30 days | How far ahead to warn about expiring SP/RIs |
| On-Demand Threshold | $100/mo | Alert when On-Demand spend exceeds this with no coverage |
| Schedule | Daily 9AM UTC | When the check runs (cron expression) |
| Scan Linked Accounts | true | Enable cross-account RI scanning |

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

## What Gets Deployed

| Resource | Purpose |
|---|---|
| Lambda | Collects data, sends email, writes to S3 |
| S3 Bucket | Daily CSV snapshots (365-day retention) |
| Glue Database + Tables | Athena-queryable tables for QuickSight |
| Athena Workgroup | Query engine |
| EventBridge Rule | Daily trigger |
| SNS Topic | Email subscription |
| IAM Role | Lambda permissions |

## Cross-Account RI Scanning

Deploy the linked account role via StackSet to enable org-wide RI visibility:

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

## Tear Down

```bash
./deploy.sh --teardown
```

## License

MIT
