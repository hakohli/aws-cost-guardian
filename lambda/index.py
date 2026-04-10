import boto3, os, json, csv, io
from datetime import datetime, timezone, timedelta
from urllib.request import Request, urlopen

NOW = datetime.now(timezone.utc)
THRESHOLD = int(os.environ.get('ALERT_DAYS', '30'))
OD_THRESHOLD = float(os.environ.get('OD_THRESHOLD', '100'))
ALERT_EMAIL = os.environ.get('ALERT_EMAIL', '')
SENDER_EMAIL = os.environ.get('SENDER_EMAIL', '')
REGION = os.environ.get('DEPLOY_REGION', 'us-east-1')
SCAN_LINKED = os.environ.get('SCAN_LINKED', 'false') == 'true'
SLACK_WEBHOOK = os.environ.get('SLACK_WEBHOOK', '')
TEAMS_WEBHOOK = os.environ.get('TEAMS_WEBHOOK', '')
DATA_BUCKET = os.environ.get('DATA_BUCKET', '')
ACCOUNT = boto3.client('sts').get_caller_identity()['Account']

def get_account_name():
    try:
        return boto3.client('organizations').describe_account(AccountId=ACCOUNT)['Account']['Name']
    except Exception:
        return ACCOUNT

def get_linked_accounts():
    if not SCAN_LINKED: return []
    try:
        accts = []
        for page in boto3.client('organizations').get_paginator('list_accounts').paginate():
            for a in page['Accounts']:
                if a['Status'] == 'ACTIVE' and a['Id'] != ACCOUNT:
                    accts.append({'id': a['Id'], 'name': a['Name']})
        return accts
    except Exception:
        return []

def assume_role(account_id):
    try:
        creds = boto3.client('sts').assume_role(
            RoleArn=f'arn:aws:iam::{account_id}:role/cost-guardian-linked-role',
            RoleSessionName='CostGuardian')['Credentials']
        return boto3.Session(aws_access_key_id=creds['AccessKeyId'],
            aws_secret_access_key=creds['SecretAccessKey'],
            aws_session_token=creds['SessionToken'])
    except Exception:
        return None

def check_savings_plans():
    rows = []
    for sp in boto3.client('savingsplans').describe_savings_plans(states=['active'])['savingsPlans']:
        end = datetime.fromisoformat(sp['end'].replace('Z', '+00:00'))
        days = (end - NOW).days
        rows.append({'type': 'SavingsPlan', 'id': sp['savingsPlanId'], 'service': sp['savingsPlanType'],
            'detail': f"${sp['commitment']}/hr", 'expires': end.strftime('%Y-%m-%d'),
            'days_remaining': days, 'account_id': ACCOUNT, 'account_name': get_account_name(),
            'status': 'expiring' if days <= THRESHOLD else 'active'})
    return rows

def check_ris_for_session(session, acct_id, acct_name):
    rows = []
    checks = [
        ('EC2', lambda s: s.client('ec2').describe_reserved_instances(
            Filters=[{'Name':'state','Values':['active']}])['ReservedInstances'],
         lambda ri: (f"{ri['InstanceCount']}x {ri['InstanceType']}",
            ri['End'] if ri['End'].tzinfo else ri['End'].replace(tzinfo=timezone.utc))),
        ('RDS', lambda s: [r for r in s.client('rds').describe_reserved_db_instances()['ReservedDBInstances'] if r['State']=='active'],
         lambda ri: (f"{ri['DBInstanceCount']}x {ri['DBInstanceClass']}",
            (ri['StartTime'] if ri['StartTime'].tzinfo else ri['StartTime'].replace(tzinfo=timezone.utc)) + timedelta(seconds=ri['Duration']))),
        ('OpenSearch', lambda s: [r for r in s.client('opensearch').describe_reserved_instances()['ReservedInstances'] if r['State']=='active'],
         lambda ri: (f"{ri['InstanceCount']}x {ri['InstanceType']}",
            (ri['StartTime'] if ri['StartTime'].tzinfo else ri['StartTime'].replace(tzinfo=timezone.utc)) + timedelta(seconds=ri['Duration']))),
        ('ElastiCache', lambda s: [r for r in s.client('elasticache').describe_reserved_cache_nodes()['ReservedCacheNodes'] if r['State']=='active'],
         lambda ri: (f"{ri['CacheNodeCount']}x {ri['CacheNodeType']}",
            (ri['StartTime'] if ri['StartTime'].tzinfo else ri['StartTime'].replace(tzinfo=timezone.utc)) + timedelta(seconds=ri['Duration']))),
        ('Redshift', lambda s: [r for r in s.client('redshift').describe_reserved_nodes()['ReservedNodes'] if r['State']=='active'],
         lambda ri: (f"{ri['NodeCount']}x {ri['NodeType']}",
            (ri['StartTime'] if ri['StartTime'].tzinfo else ri['StartTime'].replace(tzinfo=timezone.utc)) + timedelta(seconds=int(ri['Duration'])))),
    ]
    for svc, fetch, parse in checks:
        try:
            for ri in fetch(session):
                detail, end = parse(ri)
                days = (end - NOW).days
                rows.append({'type': 'ReservedInstance', 'id': '', 'service': svc, 'detail': detail,
                    'expires': end.strftime('%Y-%m-%d'), 'days_remaining': days,
                    'account_id': acct_id, 'account_name': acct_name,
                    'status': 'expiring' if days <= THRESHOLD else 'active'})
        except Exception:
            pass
    return rows

def check_on_demand():
    ce = boto3.client('ce')
    end = NOW.strftime('%Y-%m-01')
    start = (NOW.replace(day=1) - timedelta(days=1)).strftime('%Y-%m-01')
    resp = ce.get_cost_and_usage(TimePeriod={'Start': start, 'End': end}, Granularity='MONTHLY',
        Metrics=['UnblendedCost'],
        Filter={'Dimensions': {'Key': 'PURCHASE_TYPE', 'Values': ['On Demand Instances']}},
        GroupBy=[{'Type': 'DIMENSION', 'Key': 'SERVICE'}])
    svcs, total = [], 0
    for g in resp.get('ResultsByTime', [{}])[0].get('Groups', []):
        c = float(g['Metrics']['UnblendedCost']['Amount'])
        if c > 10: svcs.append({'service': g['Keys'][0], 'monthly_cost': round(c, 2)}); total += c
    svcs.sort(key=lambda x: -x['monthly_cost'])
    return svcs, round(total, 2)

def get_recommendations():
    ce, recs = boto3.client('ce'), []
    # SP recommendations
    try:
        resp = ce.get_savings_plans_purchase_recommendation(SavingsPlansType='COMPUTE_SP',
            LookbackPeriodInDays='THIRTY_DAYS', PaymentOption='NO_UPFRONT', TermInYears='ONE_YEAR')
        s = resp.get('SavingsPlansPurchaseRecommendation',{}).get('SavingsPlansPurchaseRecommendationSummary',{})
        sav = float(s.get('EstimatedMonthlySavingsAmount', 0))
        if sav > 0:
            recs.append({'type': 'Compute Savings Plan', 'term': '1yr No Upfront',
                'commitment': f"${s.get('HourlyCommitmentToPurchase','?')}/hr",
                'estimated_monthly_savings': round(sav, 2),
                'account': 'Org-wide', 'instance_detail': 'All compute'})
    except Exception: pass

    # Granular RI recommendations — per account, per instance type
    for svc, label in [('Amazon Elastic Compute Cloud - Compute','EC2'),
        ('Amazon Relational Database Service','RDS'),('Amazon OpenSearch Service','OpenSearch'),
        ('Amazon ElastiCache','ElastiCache'),('Amazon Redshift','Redshift')]:
        try:
            resp = ce.get_reservation_purchase_recommendation(Service=svc,
                LookbackPeriodInDays='THIRTY_DAYS', PaymentOption='NO_UPFRONT', TermInYears='ONE_YEAR',
                AccountScope='LINKED')
            for rec in resp.get('Recommendations', []):
                for d in rec.get('RecommendationDetails', [])[:10]:
                    sav = float(d.get('EstimatedMonthlySavingsAmount', 0))
                    if sav < 10: continue
                    acct = d.get('AccountId', 'Payer')
                    inst = d.get('InstanceDetails', {})
                    # Extract instance type from the nested structure
                    detail = ''
                    for key in inst:
                        inner = inst[key]
                        if isinstance(inner, dict):
                            itype = inner.get('InstanceType', inner.get('NodeType', inner.get('InstanceClass', '')))
                            family = inner.get('Family', '')
                            region = inner.get('Region', '')
                            count = d.get('RecommendedNumberOfInstancesToPurchase', '?')
                            detail = f"{count}x {itype}" if itype else json.dumps(inner)[:50]
                            if region: detail += f" in {region}"
                            break
                    if not detail: detail = json.dumps(inst)[:60]

                    # Resolve account name
                    acct_name = acct
                    try:
                        acct_name = boto3.client('organizations').describe_account(AccountId=acct)['Account']['Name']
                    except Exception:
                        pass

                    recs.append({
                        'type': f'{label} RI',
                        'term': '1yr No Upfront',
                        'commitment': detail,
                        'estimated_monthly_savings': round(sav, 2),
                        'account': acct,
                        'account_name': acct_name,
                        'instance_detail': detail
                    })
        except Exception: pass
    recs.sort(key=lambda x: -x['estimated_monthly_savings'])
    return recs

def collect_all():
    all_commitments = check_savings_plans()
    payer_session = boto3.Session()
    all_commitments.extend(check_ris_for_session(payer_session, ACCOUNT, get_account_name()))
    for acct in get_linked_accounts():
        session = assume_role(acct['id'])
        if session:
            all_commitments.extend(check_ris_for_session(session, acct['id'], acct['name']))
    od_svcs, od_total = check_on_demand()
    recs = get_recommendations() if od_total > OD_THRESHOLD else []
    return {'commitments': all_commitments, 'on_demand_services': od_svcs,
            'on_demand_total': od_total, 'recommendations': recs,
            'snapshot_date': NOW.strftime('%Y-%m-%d'), 'account': ACCOUNT,
            'account_name': get_account_name()}

# ============================================================
# S3 Data Export (for QuickSight / Athena)
# ============================================================
def write_to_s3(data):
    if not DATA_BUCKET: return
    s3 = boto3.client('s3')
    date_str = NOW.strftime('%Y-%m-%d')
    prefix = f"cost-guardian/{date_str}"

    # Commitments CSV
    if data['commitments']:
        buf = io.StringIO()
        w = csv.DictWriter(buf, fieldnames=['snapshot_date','type','id','service','detail','expires',
            'days_remaining','account_id','account_name','status'])
        w.writeheader()
        for r in data['commitments']:
            r['snapshot_date'] = date_str
            w.writerow(r)
        s3.put_object(Bucket=DATA_BUCKET, Key=f"{prefix}/commitments.csv",
            Body=buf.getvalue(), ContentType='text/csv')

    # On-Demand CSV
    if data['on_demand_services']:
        buf = io.StringIO()
        w = csv.DictWriter(buf, fieldnames=['snapshot_date','service','monthly_cost'])
        w.writeheader()
        for r in data['on_demand_services']:
            r['snapshot_date'] = date_str
            w.writerow(r)
        s3.put_object(Bucket=DATA_BUCKET, Key=f"{prefix}/on_demand.csv",
            Body=buf.getvalue(), ContentType='text/csv')

    # Recommendations CSV
    if data['recommendations']:
        buf = io.StringIO()
        w = csv.DictWriter(buf, fieldnames=['snapshot_date','type','term','commitment','estimated_monthly_savings'])
        w.writeheader()
        for r in data['recommendations']:
            r['snapshot_date'] = date_str
            w.writerow(r)
        s3.put_object(Bucket=DATA_BUCKET, Key=f"{prefix}/recommendations.csv",
            Body=buf.getvalue(), ContentType='text/csv')

    # Summary JSON
    summary = {'snapshot_date': date_str, 'account': data['account'], 'account_name': data['account_name'],
        'active_commitments': len(data['commitments']),
        'expiring_commitments': len([c for c in data['commitments'] if c['status'] == 'expiring']),
        'on_demand_total': data['on_demand_total'],
        'potential_savings': sum(r['estimated_monthly_savings'] for r in data['recommendations'])}
    s3.put_object(Bucket=DATA_BUCKET, Key=f"{prefix}/summary.json",
        Body=json.dumps(summary, indent=2), ContentType='application/json')

    print(f"Data written to s3://{DATA_BUCKET}/{prefix}/")

# ============================================================
# HTML Email
# ============================================================
STYLE = """<style>
body{font-family:Arial,sans-serif;color:#333;margin:0;padding:20px}
.header{background:#232f3e;color:#fff;padding:20px;border-radius:8px 8px 0 0}
.header h1{margin:0;font-size:22px}.header p{margin:5px 0 0;opacity:.8;font-size:14px}
.content{border:1px solid #ddd;border-top:none;padding:20px;border-radius:0 0 8px 8px}
.section{margin-bottom:24px}
.stitle{font-size:16px;font-weight:700;margin-bottom:10px;padding:8px 12px;border-radius:4px}
.warn{background:#fff3cd;color:#856404}.danger{background:#f8d7da;color:#721c24}
.info{background:#d1ecf1;color:#0c5460}.success{background:#d4edda;color:#155724}
table{width:100%;border-collapse:collapse;margin-top:8px;font-size:14px}
th{background:#f8f9fa;text-align:left;padding:10px 12px;border:1px solid #dee2e6;font-weight:600}
td{padding:10px 12px;border:1px solid #dee2e6}tr:nth-child(even){background:#f8f9fa}
.amt{text-align:right;font-family:monospace}
.badge{display:inline-block;padding:2px 8px;border-radius:12px;font-size:12px;font-weight:700}
.badge-red{background:#dc3545;color:#fff}.badge-yellow{background:#ffc107;color:#333}.badge-green{background:#28a745;color:#fff}
.sbox{display:inline-block;background:#f8f9fa;border:1px solid #dee2e6;border-radius:8px;padding:12px 20px;margin:4px 8px 4px 0;text-align:center}
.sbox .num{font-size:28px;font-weight:700;color:#232f3e}.sbox .lbl{font-size:11px;color:#666;text-transform:uppercase}
.footer{margin-top:20px;padding-top:16px;border-top:1px solid #ddd;font-size:12px;color:#666}
</style>"""

def days_badge(d):
    if d <= 7: return f'<span class="badge badge-red">{d}d</span>'
    if d <= 14: return f'<span class="badge badge-yellow">{d}d</span>'
    return f'<span class="badge badge-green">{d}d</span>'

def build_html(data):
    exp = [c for c in data['commitments'] if c['status'] == 'expiring']
    all_c = data['commitments']
    od_svcs, od_total = data['on_demand_services'], data['on_demand_total']
    recs = data['recommendations']

    html = f"""<html><head>{STYLE}</head><body>
    <div class="header"><h1>AWS Cost Guardian</h1>
    <p>{data['account_name']} ({data['account']}) | {REGION} | {NOW:%B %d, %Y}</p></div>
    <div class="content">
    <div style="margin-bottom:20px">
      <div class="sbox"><div class="num">{len(exp)}</div><div class="lbl">Expiring</div></div>
      <div class="sbox"><div class="num">{len(all_c)}</div><div class="lbl">Active SP/RI</div></div>
      <div class="sbox"><div class="num">${od_total:,.0f}</div><div class="lbl">On-Demand/mo</div></div>
      <div class="sbox"><div class="num">${sum(r['estimated_monthly_savings'] for r in recs):,.0f}</div><div class="lbl">Potential Savings</div></div>
    </div>"""

    if exp:
        sps = [c for c in exp if c['type'] == 'SavingsPlan']
        ris = [c for c in exp if c['type'] == 'ReservedInstance']
        if sps:
            html += '<div class="section"><div class="stitle warn">&#9888;&#65039; Savings Plans Expiring</div>'
            html += '<table><tr><th>Type</th><th>Commitment</th><th>Expires</th><th>Days</th></tr>'
            for r in sorted(sps, key=lambda x: x['days_remaining']):
                html += f"<tr><td>{r['service']}</td><td class='amt'>{r['detail']}</td><td>{r['expires']}</td><td>{days_badge(r['days_remaining'])}</td></tr>"
            html += '</table></div>'
        if ris:
            html += '<div class="section"><div class="stitle warn">&#9888;&#65039; Reserved Instances Expiring</div>'
            html += '<table><tr><th>Account</th><th>Service</th><th>Details</th><th>Expires</th><th>Days</th></tr>'
            for r in sorted(ris, key=lambda x: x['days_remaining']):
                html += f"<tr><td>{r['account_name']}</td><td>{r['service']}</td><td>{r['detail']}</td><td>{r['expires']}</td><td>{days_badge(r['days_remaining'])}</td></tr>"
            html += '</table></div>'

    if od_total > OD_THRESHOLD:
        no_cov = len(all_c) == 0
        html += f'<div class="section"><div class="stitle danger">&#128176; On-Demand: ${od_total:,.0f}/mo</div>'
        if no_cov:
            html += '<p style="color:#dc3545;font-weight:700">&#10060; No active Savings Plans or Reserved Instances</p>'
        html += '<table><tr><th>Service</th><th style="text-align:right">Monthly</th><th style="text-align:right">%</th></tr>'
        for s in od_svcs[:10]:
            pct = s['monthly_cost']/od_total*100 if od_total else 0
            html += f'<tr><td>{s["service"]}</td><td class="amt">${s["monthly_cost"]:,.0f}</td><td class="amt">{pct:.1f}%</td></tr>'
        html += '</table></div>'

    if recs:
        html += '<div class="section"><div class="stitle info">&#128203; Recommendations</div>'
        html += '<table><tr><th>Type</th><th>Term</th><th>Commitment</th><th style="text-align:right">Savings/mo</th></tr>'
        for r in recs:
            html += f"<tr><td>{r['type']}</td><td>{r['term']}</td><td>{r['commitment']}</td><td class='amt' style='color:#28a745;font-weight:700'>${r['estimated_monthly_savings']:,.0f}</td></tr>"
        html += '</table></div>'

    if not exp and od_total <= OD_THRESHOLD:
        html += '<div class="section"><div class="stitle success">&#9989; All Clear</div></div>'

    html += f"""<div class="footer">
      <p><a href="https://{REGION}.console.aws.amazon.com/cost-management/home#/savings-plans/recommendations">SP Recs</a>
      | <a href="https://{REGION}.console.aws.amazon.com/cost-management/home#/reservations/recommendations">RI Recs</a>
      | <a href="https://{REGION}.console.aws.amazon.com/cost-management/home#/cost-explorer">Cost Explorer</a></p>
    </div></div></body></html>"""
    return html

def send_email(data):
    exp = [c for c in data['commitments'] if c['status'] == 'expiring']
    needs_alert = bool(exp) or data['on_demand_total'] > OD_THRESHOLD
    if not needs_alert:
        print("All clear — no email needed")
        return
    html = build_html(data)
    subj = f"[{ACCOUNT}] Cost Guardian"
    if exp: subj += f" — {len(exp)} Expiring"
    if data['on_demand_total'] > OD_THRESHOLD and not data['commitments']:
        subj += f" — ${data['on_demand_total']:,.0f}/mo No Coverage"
    boto3.client('ses', region_name=REGION).send_email(
        Source=SENDER_EMAIL, Destination={'ToAddresses': [ALERT_EMAIL]},
        Message={'Subject': {'Data': subj}, 'Body': {'Html': {'Data': html}}})
    print(f"Alert sent to {ALERT_EMAIL}")

# ============================================================
# Handler
# ============================================================
def handler(event, context):
    action = event.get('action', 'alert')
    data = collect_all()

    # Always write to S3 for QuickSight
    write_to_s3(data)

    if action == 'query':
        query = event.get('query', '').lower()
        if 'expir' in query:
            exp = [c for c in data['commitments'] if c['status'] == 'expiring']
            return {'answer': f"{len(exp)} SP/RIs expiring within {THRESHOLD} days", 'details': exp}
        if 'recommend' in query:
            return {'answer': f"{len(data['recommendations'])} recommendations", 'details': data['recommendations']}
        if 'on-demand' in query or 'coverage' in query:
            return {'answer': f"${data['on_demand_total']:,.0f}/mo On-Demand", 'services': data['on_demand_services'][:10]}
        if 'summary' in query or 'status' in query:
            return {'account': data['account_name'], 'active_commitments': len(data['commitments']),
                'expiring': len([c for c in data['commitments'] if c['status']=='expiring']),
                'on_demand_monthly': f"${data['on_demand_total']:,.0f}",
                'potential_savings': f"${sum(r['estimated_monthly_savings'] for r in data['recommendations']):,.0f}/mo"}
        return data

    # Alert mode
    send_email(data)
    exp = [c for c in data['commitments'] if c['status'] == 'expiring']
    return {'expiring': len(exp), 'on_demand_total': data['on_demand_total'],
            'alerted': bool(exp) or data['on_demand_total'] > OD_THRESHOLD}

def send_email(data):
    exp = [c for c in data['commitments'] if c['status'] == 'expiring']
    needs_alert = bool(exp) or data['on_demand_total'] > OD_THRESHOLD
    if not needs_alert:
        print("All clear — no email needed")
        return
    html = build_html(data)
    subj = f"[{ACCOUNT}] Cost Guardian"
    if exp: subj += f" — {len(exp)} Expiring"
    if data['on_demand_total'] > OD_THRESHOLD and not data['commitments']:
        subj += f" — ${data['on_demand_total']:,.0f}/mo No Coverage"
    boto3.client('ses', region_name=REGION).send_email(
        Source=SENDER_EMAIL, Destination={'ToAddresses': [ALERT_EMAIL]},
        Message={'Subject': {'Data': subj}, 'Body': {'Html': {'Data': html}}})
    print(f"Email sent to {ALERT_EMAIL}")

# ============================================================
# Slack / Teams Notifications
# ============================================================
def send_webhook(url, payload):
    req = Request(url, data=json.dumps(payload).encode(), headers={'Content-Type': 'application/json'})
    urlopen(req)

def send_slack(data):
    if not SLACK_WEBHOOK: return
    exp = [c for c in data['commitments'] if c['status'] == 'expiring']
    recs = data['recommendations']
    blocks = [
        {"type": "header", "text": {"type": "plain_text", "text": f"💰 Cost Guardian — {data['account_name']} ({ACCOUNT})"}},
        {"type": "section", "fields": [
            {"type": "mrkdwn", "text": f"*Expiring SP/RI:*\n{len(exp)}"},
            {"type": "mrkdwn", "text": f"*Active SP/RI:*\n{len(data['commitments'])}"},
            {"type": "mrkdwn", "text": f"*On-Demand/mo:*\n${data['on_demand_total']:,.0f}"},
            {"type": "mrkdwn", "text": f"*Potential Savings:*\n${sum(r['estimated_monthly_savings'] for r in recs):,.0f}/mo"},
        ]},
    ]

    if exp:
        lines = [f"• *{c['service']}* {c['detail']} — expires {c['expires']} ({c['days_remaining']}d)" for c in sorted(exp, key=lambda x: x['days_remaining'])[:10]]
        blocks.append({"type": "section", "text": {"type": "mrkdwn", "text": f"*⚠️ Expiring Commitments*\n" + "\n".join(lines)}})

    if recs:
        lines = [f"• *{r.get('account_name', r.get('account',''))}*: Buy {r['commitment']} ({r['type']}) → saves *${r['estimated_monthly_savings']:,.0f}/mo*" for r in recs[:10]]
        blocks.append({"type": "section", "text": {"type": "mrkdwn", "text": f"*📋 Recommendations*\n" + "\n".join(lines)}})

    if data['on_demand_total'] > OD_THRESHOLD:
        top = data['on_demand_services'][:5]
        lines = [f"• {s['service']}: ${s['monthly_cost']:,.0f}" for s in top]
        blocks.append({"type": "section", "text": {"type": "mrkdwn", "text": f"*🔴 Top On-Demand Spend*\n" + "\n".join(lines)}})

    blocks.append({"type": "context", "elements": [
        {"type": "mrkdwn", "text": f"<https://{REGION}.console.aws.amazon.com/cost-management/home#/savings-plans/recommendations|SP Recs> | <https://{REGION}.console.aws.amazon.com/cost-management/home#/reservations/recommendations|RI Recs> | Threshold: {THRESHOLD}d / ${OD_THRESHOLD:,.0f}"}
    ]})

    send_webhook(SLACK_WEBHOOK, {"blocks": blocks})
    print("Slack notification sent")

def send_teams(data):
    if not TEAMS_WEBHOOK: return
    exp = [c for c in data['commitments'] if c['status'] == 'expiring']
    recs = data['recommendations']

    sections = [{"activityTitle": f"Cost Guardian — {data['account_name']} ({ACCOUNT})",
        "facts": [
            {"name": "Expiring SP/RI", "value": str(len(exp))},
            {"name": "Active SP/RI", "value": str(len(data['commitments']))},
            {"name": "On-Demand/mo", "value": f"${data['on_demand_total']:,.0f}"},
            {"name": "Potential Savings", "value": f"${sum(r['estimated_monthly_savings'] for r in recs):,.0f}/mo"},
        ]}]

    if exp:
        facts = [{"name": f"{c['service']} {c['detail']}", "value": f"Expires {c['expires']} ({c['days_remaining']}d)"}
                 for c in sorted(exp, key=lambda x: x['days_remaining'])[:10]]
        sections.append({"activityTitle": "⚠️ Expiring Commitments", "facts": facts})

    if recs:
        facts = [{"name": f"{r.get('account_name','')}: {r['commitment']}", "value": f"${r['estimated_monthly_savings']:,.0f}/mo savings"}
                 for r in recs[:10]]
        sections.append({"activityTitle": "📋 Recommendations", "facts": facts})

    card = {"@type": "MessageCard", "@context": "http://schema.org/extensions",
        "themeColor": "FF9900", "summary": f"Cost Guardian — {len(exp)} expiring",
        "sections": sections,
        "potentialAction": [{"@type": "OpenUri", "name": "Open Cost Explorer",
            "targets": [{"os": "default", "uri": f"https://{REGION}.console.aws.amazon.com/cost-management/home"}]}]}

    send_webhook(TEAMS_WEBHOOK, card)
    print("Teams notification sent")

# ============================================================
# Handler
# ============================================================
def handler(event, context):
    action = event.get('action', 'alert')
    data = collect_all()

    # Always write to S3 for QuickSight
    write_to_s3(data)

    if action == 'query':
        query = event.get('query', '').lower()
        if 'expir' in query:
            exp = [c for c in data['commitments'] if c['status'] == 'expiring']
            return {'answer': f"{len(exp)} SP/RIs expiring within {THRESHOLD} days", 'details': exp}
        if 'recommend' in query:
            return {'answer': f"{len(data['recommendations'])} recommendations", 'details': data['recommendations']}
        if 'on-demand' in query or 'coverage' in query:
            return {'answer': f"${data['on_demand_total']:,.0f}/mo On-Demand", 'services': data['on_demand_services'][:10]}
        if 'summary' in query or 'status' in query:
            return {'account': data['account_name'], 'active_commitments': len(data['commitments']),
                'expiring': len([c for c in data['commitments'] if c['status']=='expiring']),
                'on_demand_monthly': f"${data['on_demand_total']:,.0f}",
                'potential_savings': f"${sum(r['estimated_monthly_savings'] for r in data['recommendations']):,.0f}/mo"}
        return data

    # Alert mode — send to all configured channels
    exp = [c for c in data['commitments'] if c['status'] == 'expiring']
    needs_alert = bool(exp) or data['on_demand_total'] > OD_THRESHOLD

    if needs_alert:
        send_email(data)
        send_slack(data)
        send_teams(data)

    return {'expiring': len(exp), 'on_demand_total': data['on_demand_total'], 'alerted': needs_alert}
