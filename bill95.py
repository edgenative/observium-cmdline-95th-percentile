#!/usr/bin/env python3
import sys
import argparse
import datetime
import numpy as np
import rrdtool
import smtplib
import re
import mysql.connector
from email.mime.text import MIMEText
from collections import defaultdict
import os

# Script for generating 95th Percentile reports from your Observium Instance
# (c) 2025 Lee Hetherington <lee@edgenative.net>

# ---------------------- SMTP Configuration ----------------------
SMTP_HOST = "localhost"
SMTP_PORT = 25  # Default unauthenticated SMTP port
SMTP_SENDER = "billing@yourdomain.net"
# ---------------------- RRD 95th percentile calculation ----------------------
def compute_95th(rrd_file, start_ts, end_ts):
    (start, end, step), names, data = rrdtool.fetch(
        rrd_file, "AVERAGE", "--start", str(start_ts), "--end", str(end_ts)
    )

    if len(names) < 2:
        raise ValueError(f"RRD {rrd_file} must have at least two DS (in/out)")

    in_idx, out_idx = 0, 1
    combined_vals = [max(row[in_idx], row[out_idx]) for row in data
                     if row[in_idx] is not None and row[out_idx] is not None]

    if not combined_vals:
        return 0.0

    combined_vals = np.array(combined_vals) * 8 / 1e6  # Convert to Mbps
    return np.percentile(combined_vals, 95)

# ---------------------- Date range calculation ----------------------
def get_date_range(prev_month=False):
    now = datetime.datetime.now()
    if prev_month:
        first_this_month = datetime.datetime(now.year, now.month, 1)
        last_month_end = first_this_month - datetime.timedelta(seconds=1)
        last_month_start = datetime.datetime(last_month_end.year,
                                             last_month_end.month, 1)
        return int(last_month_start.timestamp()), int(last_month_end.timestamp())
    else:
        start_month = datetime.datetime(now.year, now.month, 1)
        return int(start_month.timestamp()), int(now.timestamp())

# ---------------------- Month label ----------------------
def get_month_label(prev_month=False):
    now = datetime.datetime.now()
    if prev_month:
        first_this_month = datetime.datetime(now.year, now.month, 1)
        last_month_end = first_this_month - datetime.timedelta(seconds=1)
        return last_month_end.strftime("%B %Y")  # e.g., "August 2025"
    else:
        return now.strftime("%B %Y")  # current month

# ---------------------- Email ----------------------
def send_email(to_addr, subject, body):
    msg = MIMEText(body)
    msg["From"] = SMTP_SENDER
    msg["To"] = to_addr
    msg["Subject"] = subject

    # No authentication required
    with smtplib.SMTP(SMTP_HOST, SMTP_PORT) as s:
        s.send_message(msg)

# ---------------------- Observium DB ----------------------
def load_observium_db_config(config_path):
    db_config = {}
    with open(config_path) as f:
        content = f.read()
        db_config['host'] = re.search(r"\$config\['db_host'\]\s*=\s*'([^']+)'", content).group(1)
        db_config['user'] = re.search(r"\$config\['db_user'\]\s*=\s*'([^']+)'", content).group(1)
        db_config['password'] = re.search(r"\$config\['db_pass'\]\s*=\s*'([^']+)'", content).group(1)
        db_config['database'] = re.search(r"\$config\['db_name'\]\s*=\s*'([^']+)'", content).group(1)
    return db_config

def load_customer_interfaces(db_config, rrd_base="/opt/observium/rrd"):
    conn = mysql.connector.connect(**db_config)
    cur = conn.cursor(dictionary=True)

    # Query interfaces whose ifAlias starts with 'Cust:'
    query = """
        SELECT p.ifIndex, p.ifAlias, d.hostname
        FROM ports AS p
        JOIN devices AS d ON p.device_id = d.device_id
        WHERE p.ifAlias REGEXP '^[Cc]ust:'
    """
    cur.execute(query)
    rows = cur.fetchall()
    cur.close()
    conn.close()

    if not rows:
        print("Warning: No interfaces found with ifAlias starting with 'Cust:'")
        return {}

    customers = defaultdict(list)
    for r in rows:
        alias = r['ifAlias']
        try:
            cust_name = alias.split(":", 1)[1].strip()
        except IndexError:
            cust_name = "Unknown"

        # Use ifIndex for RRD filename: port-<ifIndex>.rrd
        rrd_file = os.path.join(rrd_base, r['hostname'], f"port-{r['ifIndex']}.rrd")
        if os.path.exists(rrd_file):
            customers[cust_name].append(rrd_file)
        else:
            print(f"Warning: RRD file not found for interface '{alias}': {rrd_file}")

    return customers

# ---------------------- Main ----------------------
def main():
    parser = argparse.ArgumentParser(description="95th percentile billing calculator")
    parser.add_argument("--observium-config", help="Path to Observium config.php", required=True)
    parser.add_argument("--prev", action="store_true", help="Use previous month")
    parser.add_argument("--email", help="Email address to send results")
    parser.add_argument("--rrd-base", help="Base path for RRD files", default="/opt/observium/rrd")
    args = parser.parse_args()

    start_ts, end_ts = get_date_range(args.prev)
    month_label = get_month_label(args.prev)

    db_config = load_observium_db_config(args.observium_config)
    customers = load_customer_interfaces(db_config, rrd_base=args.rrd_base)

    if not customers:
        print("No customers with RRDs found. Exiting.")
        return

    lines = []
    for cust_name, rrd_list in customers.items():
        combined_samples = []
        for rrd in rrd_list:
            try:
                val = compute_95th(rrd, start_ts, end_ts)
                combined_samples.append(val)
            except Exception as e:
                print(f"Error reading {rrd}: {e}")
        if combined_samples:
            val_95 = max(combined_samples)
        else:
            val_95 = 0.0
        lines.append(f"{cust_name}: {val_95:.2f} Mbps")

    header = f"95th Percentile Billing Report for {month_label}\n"
    report = header + "\n" + "\n".join(lines)

    if args.email:
        send_email(args.email, f"95th Percentile Billing Report for {month_label}", report)
    else:
        print(report)

if __name__ == "__main__":
    main()
