import sched
import time
import requests
import json
import os
from datetime import datetime, timedelta
import pytz
import smtplib
from email.mime.multipart import MIMEMultipart
from email.mime.text import MIMEText

# Hardcoded Firebase client config
def get_firebase_config():
    return {
        "apiKey": "AIzaSyB_bcgnPIiUdfbwl90P5akK1H9OaNsPcqM",
        "databaseURL": "https://rcdclist-dea80-default-rtdb.firebaseio.com"
    }

# Email credentials and recipients
def get_email_config():
    return {
        "smtp_server": "smtp.gmail.com",
        "smtp_port": 587,
        "username": "touheedfarid@gmail.com",
        "password": "bztk umfx dart zdmd",  # plain password as requested
        "from_addr": "touheedfarid@gmail.com",
        "to_addrs": ["huzaifawaseem578@gmail.com"]
    }

# Fetch feeder records via REST API
def fetch_feeder_data():
    url = f"{get_firebase_config()['databaseURL']}/feeders.json"
    try:
        resp = requests.get(url)
        resp.raise_for_status()
        return resp.json() or {}
    except requests.RequestException as e:
        print(f"HTTP error fetching feeder data: {e}")
        return {}

# Fetch adjusted times list from DB
def fetch_adjusted_times():
    url = f"{get_firebase_config()['databaseURL']}/uniqueTimes.json"
    try:
        resp = requests.get(url)
        resp.raise_for_status()
        return resp.json() or []
    except requests.RequestException as e:
        print(f"HTTP error fetching adjusted times: {e}")
        return []

# Adjust time string by given delta minutes
def shift_time(time_str, minutes):
    try:
        dt = datetime.strptime(time_str, "%H:%M")
        return (dt + timedelta(minutes=minutes)).strftime("%H:%M")
    except Exception:
        return time_str

# Generate HTML table for email report with rounded corners and styled header
def build_html_table(matches):
    # Hex color mapping
    ibc_colors = {
        "JOHAR 1": "#90EE90",  # lightgreen
        "JOHAR 2": "#ADD8E6",  # lightblue
        "GADAP": "#FFFFE0"     # lightyellow
    }
    table_style = (
        "border-collapse: separate;"
        "border-spacing: 0;"
        "border-radius: 8px;"
        "overflow: hidden;"
    )
    header_style = (
        "background-color: #fa9522;"
        "color: #FFFFFF;"
    )
    html = [
        "<html><body>",
        "<h2>Feeder Event Report</h2>",
        f"<table style='{table_style}' border='1' cellpadding='5' cellspacing='0'>",
        (
            "<tr style='" + header_style + "'>"
            "<th>Name</th><th>Event</th><th>Duration</th><th>Type</th>"
            "<th>OFF Time</th><th>ON Time</th><th>IBC</th><th>Grid</th><th>Hold Reason</th></tr>"
        )
    ]
    for rec_id, rec, event in matches:
        # Determine row color: red for HOLD (#FF0000), otherwise by IBC
        color = "#FF0000" if event == 'HOLD' else ibc_colors.get(rec.get('IBC'), "#000000")
        html.append(f"<tr style='background-color:{color};'>")
        html.append(f"<td>{rec.get('feederName')}</td>")
        html.append(f"<td>{event}</td>")
        html.append(f"<td>{rec.get('duration')}</td>")
        html.append(f"<td>{rec.get('type')}</td>")
        html.append(f"<td>{rec.get('offTime')}</td>")
        html.append(f"<td>{rec.get('onTime')}</td>")
        html.append(f"<td>{rec.get('IBC')}</td>")
        html.append(f"<td>{rec.get('Grid')}</td>")
        html.append(f"<td>{rec.get('hold_reason')}</td>")
        html.append("</tr>")
    html.append("</table></body></html>")
    return '\n'.join(html)

# Send email with HTML content
def send_email(html_content):
    cfg = get_email_config()
    msg = MIMEMultipart('alternative')
    msg['Subject'] = 'Instant Feeder Event Notification'
    msg['From'] = cfg['from_addr']
    msg['To'] = ', '.join(cfg['to_addrs'])
    msg.attach(MIMEText(html_content, 'html'))
    try:
        with smtplib.SMTP(cfg['smtp_server'], cfg['smtp_port']) as server:
            server.starttls()
            server.login(cfg['username'], cfg['password'])
            server.sendmail(cfg['from_addr'], cfg['to_addrs'], msg.as_string())
        print("Email sent successfully.")
    except Exception as e:
        print(f"Error sending email: {e}")

# Job: pull feeders and store adjusted times every 5 minutes
def update_adjusted_times():
    tz = pytz.timezone('Asia/Karachi')
    now = datetime.now(tz)
    print(f"\nUpdating adjusted times at {now.strftime('%Y-%m-%d %H:%M:%S %Z')}")
    data = fetch_feeder_data()
    if not data:
        print("No feeder data fetched.")
        return
    unique = {val for rec in data.values() for key in ('offTime','onTime') if (val:=rec.get(key))}
    adjusted = [shift_time(t, -6) for t in sorted(unique)]
    print(f"Storing {len(adjusted)} adjusted times.")
    requests.put(f"{get_firebase_config()['databaseURL']}/uniqueTimes.json", json.dumps(adjusted))

# Watcher: every 30s, match current time, notify via email
def watch_times():
    tz = pytz.timezone('Asia/Karachi')
    now_str = datetime.now(tz).strftime('%H:%M')
    adjusted = fetch_adjusted_times()
    if now_str in adjusted:
        target = shift_time(now_str, 6)
        print(f"\nMatch at {now_str}. Fetching feeders for time {target}.")
        matches = []
        for rec_id, rec in fetch_feeder_data().items():
            if rec.get('offTime') == target or rec.get('onTime') == target:
                event = 'HOLD' if rec.get('on_hold') else ('OFF' if rec.get('offTime') == target else 'ON')
                matches.append((rec_id, rec, event))
        if matches:
            html = build_html_table(matches)
            send_email(html)
        else:
            print("No feeders matched target time.")

if __name__ == '__main__':
    scheduler = sched.scheduler(time.time, time.sleep)
    scheduler.enter(0,1,update_adjusted_times)
    def upd():
        update_adjusted_times()
        scheduler.enter(300,1,upd)
    scheduler.enter(300,1,upd)
    scheduler.enter(0,2,watch_times)
    def wch():
        watch_times()
        scheduler.enter(30,2,wch)
    scheduler.enter(30,2,wch)
    print("Scheduler started: updater every 5min, watcher every 30s.")
    try:
        scheduler.run()
    except (KeyboardInterrupt, SystemExit):
        print("Scheduler stopped.")
