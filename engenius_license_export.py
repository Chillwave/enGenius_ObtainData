#!/usr/bin/env python3
"""
EnGenius Cloud License Export
Exports device license info sorted by expiration date

Usage:
    1. Put your API key in api_key.txt (same directory)
    2. Run: python3 engenius_license_export.py
"""

import requests
import sys
import os
import csv
import time
from datetime import datetime

# =============================================================================
# CONFIGURATION
# =============================================================================
BASE_URL = "https://falcon.production.engenius.ai/v2"
MAX_RETRIES = 3
RETRY_DELAY = 2

def load_api_key():
    key_files = ["api_key.txt", "apikey.txt", "API_KEY.txt"]
    for f in key_files:
        if os.path.exists(f):
            with open(f, 'r') as file:
                key = file.read().strip()
                print(f"[+] Loaded API key from {f} ({len(key)} chars)")
                return key
    print("[!] ERROR: No api_key.txt found!")
    sys.exit(1)

API_KEY = load_api_key()

# =============================================================================
# API CLIENT
# =============================================================================
session = requests.Session()
session.headers.update({
    "api-key": API_KEY,
    "Content-Type": "application/json",
    "Accept": "application/json"
})

def api_get(endpoint, params=None):
    url = f"{BASE_URL}{endpoint}"
    
    for attempt in range(MAX_RETRIES):
        try:
            resp = session.get(url, params=params, timeout=30)
            
            if resp.status_code == 200:
                return resp.json()
            elif resp.status_code == 503:
                if attempt < MAX_RETRIES - 1:
                    print(f"[503] Retry {attempt + 1}/{MAX_RETRIES}...", end=" ", flush=True)
                    time.sleep(RETRY_DELAY)
                    continue
                else:
                    return None
            else:
                print(f"[{resp.status_code}]", end=" ")
                return None
        except Exception as e:
            if attempt < MAX_RETRIES - 1:
                time.sleep(RETRY_DELAY)
            else:
                return None
    return None

def timestamp_to_date(ts):
    """Convert millisecond timestamp to date string"""
    if ts is None:
        return ""
    try:
        return datetime.fromtimestamp(ts / 1000).strftime("%Y-%m-%d")
    except:
        return ""

def days_until_expiration(ts):
    """Calculate days until expiration (negative = expired)"""
    if ts is None:
        return None
    try:
        exp_date = datetime.fromtimestamp(ts / 1000)
        delta = exp_date - datetime.now()
        return delta.days
    except:
        return None

# =============================================================================
# MAIN
# =============================================================================
print("=" * 70)
print("EnGenius Cloud License Export")
print("=" * 70)

all_devices = []

# Get organizations
print("\n[1] Getting organizations...")
orgs = api_get("/user/orgs")
if not orgs:
    print("ERROR: Could not get organizations")
    sys.exit(1)

if isinstance(orgs, dict):
    orgs = [orgs]

print(f"    Found {len(orgs)} organization(s)")

for org in orgs:
    org_id = org.get("id") or org.get("_id")
    org_name = org.get("name", "Unknown")
    print(f"\n[ORG] {org_name}")
    
    # Get inventory (all devices with license info)
    print("    Getting inventory...", end=" ", flush=True)
    inventory = api_get(f"/orgs/{org_id}/inventory", params={"count": 1000})
    
    if not inventory:
        print("(no data)")
        continue
    
    # Handle response format
    if isinstance(inventory, dict):
        devices = inventory.get("devices", [])
    else:
        devices = inventory
    
    print(f"({len(devices)} devices)")
    
    for device in devices:
        expired_date = device.get("expired_date")
        days_left = days_until_expiration(expired_date)
        
        all_devices.append({
            "organization": org_name,
            "network_name": device.get("network_name", ""),
            "device_name": device.get("name", ""),
            "device_type": device.get("type", ""),
            "model": device.get("model", ""),
            "mac": device.get("mac", ""),
            "serial_number": device.get("serial_number", ""),
            "license_status": device.get("license_status", ""),
            "expiration_date": timestamp_to_date(expired_date),
            "days_until_expiration": days_left if days_left is not None else "",
        })

# =============================================================================
# SORT BY EXPIRATION (expired first, then soonest expiring)
# =============================================================================
def sort_key(d):
    days = d["days_until_expiration"]
    if days == "":
        return 99999  # No expiration date goes last
    return days

all_devices.sort(key=sort_key)

# =============================================================================
# EXPORT TO CSV
# =============================================================================
print("\n" + "=" * 70)
print("EXPORT")
print("=" * 70)

if not all_devices:
    print("No devices found!")
    sys.exit(1)

timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
filename = f"engenius_licenses_{timestamp}.csv"

fieldnames = [
    "organization", "network_name", "device_name", "device_type", "model",
    "mac", "serial_number", "license_status", "expiration_date", "days_until_expiration"
]

with open(filename, "w", newline="") as f:
    writer = csv.DictWriter(f, fieldnames=fieldnames)
    writer.writeheader()
    writer.writerows(all_devices)

print(f"\n[+] Exported {len(all_devices)} devices to: {filename}")

# Summary
print(f"\nSummary:")
print(f"  Total Devices: {len(all_devices)}")

# License status breakdown
statuses = {}
for d in all_devices:
    s = d["license_status"] or "unknown"
    statuses[s] = statuses.get(s, 0) + 1

print(f"\n  License Status:")
for status, count in sorted(statuses.items(), key=lambda x: -x[1]):
    print(f"    {status}: {count}")

# Show expired/expiring soon
expired = [d for d in all_devices if d["days_until_expiration"] != "" and d["days_until_expiration"] < 0]
expiring_30 = [d for d in all_devices if d["days_until_expiration"] != "" and 0 <= d["days_until_expiration"] <= 30]

if expired:
    print(f"\n  !!!  EXPIRED: {len(expired)} devices")
    for d in expired[:10]:  # Show first 10
        print(f"    - {d['device_name']} ({d['device_type']}) - expired {abs(d['days_until_expiration'])} days ago")
    if len(expired) > 10:
        print(f"    ... and {len(expired) - 10} more")

if expiring_30:
    print(f"\n  ! EXPIRING WITHIN 30 DAYS: {len(expiring_30)} devices")
    for d in expiring_30[:10]:
        print(f"    - {d['device_name']} ({d['device_type']}) - {d['days_until_expiration']} days left")
    if len(expiring_30) > 10:
        print(f"    ... and {len(expiring_30) - 10} more")

print(f"\n[+] Done!")
