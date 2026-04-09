# QuickSight Chat Agent Setup Guide

After deploying the CloudFormation stack, follow these steps to create the interactive Cost Guardian chat agent in Amazon Quick.

## Step 1: Create QuickSight Datasets

In QuickSight console → Datasets → New Dataset → Athena:

**Dataset 1: Commitments**
- Data source: Athena
- Workgroup: `cost-guardian`
- Database: `cost_guardian`
- Table: `commitments`
- Import to SPICE (recommended for performance)
- Schedule: Daily refresh

**Dataset 2: On-Demand Spend**
- Table: `on_demand_spend`
- Same settings as above

**Dataset 3: Recommendations**
- Table: `recommendations`
- Same settings as above

## Step 2: Create Dashboard

Create a QuickSight analysis with these visuals:

### Sheet 1: Overview
- **KPI**: Total expiring SP/RIs (filter: status = 'expiring')
- **KPI**: Total active commitments
- **KPI**: Total On-Demand spend
- **KPI**: Total potential savings

### Sheet 2: Commitments
- **Table**: All commitments with columns: Account, Service, Type, Detail, Expires, Days Remaining, Status
- **Bar chart**: Commitments by service, colored by status (active/expiring)
- **Timeline**: Expiration dates on a Gantt-style chart

### Sheet 3: On-Demand Spend
- **Pie chart**: On-Demand spend by service
- **Line chart**: On-Demand spend trend over time (daily snapshots)
- **Table**: Service breakdown with monthly cost

### Sheet 4: Recommendations
- **Table**: All recommendations with type, term, commitment, estimated savings
- **Bar chart**: Savings by recommendation type

Publish the analysis as a dashboard.

## Step 3: Create Custom Chat Agent

In Amazon Quick console:

1. Go to **Chat Agents** (left nav)
2. Click **Create custom chat agent**
3. Configure:

**Name**: `Cost Guardian`

**Description**: `AI assistant for AWS cost optimization — monitors Savings Plans, Reserved Instances, On-Demand spend, and purchase recommendations.`

**Custom Instructions**:
```
You are Cost Guardian, an AWS cost optimization assistant. You help users understand their Savings Plans and Reserved Instance status, identify expiring commitments, analyze On-Demand spend, and recommend cost-saving actions.

When answering questions:
- Always mention specific dollar amounts and dates
- Flag anything expiring within 30 days as urgent
- When showing On-Demand spend, include the percentage of total
- When discussing recommendations, include estimated monthly savings
- If asked about trends, compare the most recent snapshot to earlier ones
- Use tables for structured data
- Be concise and actionable

Key terminology:
- "SP" or "Savings Plan" = Savings Plans commitments
- "RI" or "Reserved Instance" = Reserved Instances (EC2, RDS, OpenSearch, ElastiCache, Redshift)
- "expiring" = days_remaining <= 30
- "coverage" = having active SPs or RIs vs On-Demand
- "On-Demand" = pay-as-you-go without commitments
```

**Linked Data Sources**:
- Select the `commitments` dataset
- Select the `on_demand_spend` dataset
- Select the `recommendations` dataset
- Select the Cost Guardian dashboard

4. Click **Create**
5. **Share** the agent with your team

## Step 4: Test the Chat Agent

Open the Cost Guardian chat agent and try these questions:

```
"Show me all expiring commitments"
"What's our total On-Demand spend?"
"Which services cost the most on On-Demand?"
"Do we have any recommendations to save money?"
"What accounts have expiring RIs?"
"Show me the On-Demand spend trend"
"How much could we save with Savings Plans?"
"Are there any RIs expiring this month?"
"Compare our coverage this week vs last week"
"What's the summary of our cost optimization status?"
```

## Step 5: Share with Team

1. In the chat agent settings, click **Share**
2. Add users or groups (finance team, ops team, leadership)
3. Users access it from Amazon Quick → Chat → Cost Guardian

## Architecture

```
Lambda (daily 9AM UTC)
  ├── Email alert (SES) → ops team
  ├── S3 data export → CSV files
  │     └── Athena tables
  │           └── QuickSight datasets
  │                 ├── Dashboard (visual)
  │                 └── Custom Chat Agent (conversational)
  └── CLI query (./query.sh)
```

## Data Refresh

- Lambda runs daily → writes fresh CSV to S3
- QuickSight SPICE dataset refreshes daily (configure in dataset settings)
- Chat agent always queries latest SPICE data
- Historical data accumulates in S3 (365-day retention)
