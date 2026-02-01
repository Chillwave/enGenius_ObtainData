#!/usr/bin/env python3
"""
EnGenius Switch Extender Export
Finds all switch extenders via inventory API and exports to CSV.

Switch extenders have no dedicated /devices/ endpoint and no online/offline
status in the API. This script queries the inventory with type=switch_extender
to pull what is available: name, model, MAC, serial, network, and license status.

Usage:
    python3 engenius_switch_extender_export.py
"""

import requests
import sys
import os
import csv
import time
from datetime import datetime

BASE_URL = "https://falcon.production.engenius.ai/v2"
MAX_RETRIES = 3
RETRY_DELAY = 2


def load_api_key():
    for f in ["api_key.txt", "apikey.txt", "API_KEY.txt"]:
        if os.path.exists(f):
            with open(f, 'r') as file:
                key = file.read().strip()
                print(f"[INFO] Loaded API key from {f}")
                return key
    print("[ERROR] No api_key.txt found")
    sys.exit(1)


API_KEY = load_api_key()

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
            elif resp.status_code == 406:
                print(f"[ERROR] 406 Not Acceptable - expired API key or unauthorized IP")
                return None
            elif resp.status_code == 503:
                if attempt < MAX_RETRIES - 1:
                    print(f"[WARN] 503, retry {attempt + 1}/{MAX_RETRIES}...")
                    time.sleep(RETRY_DELAY)
                    continue
            else:
                print(f"[WARN] {resp.status_code} for {endpoint}")
            return None
        except Exception as e:
            if attempt < MAX_RETRIES - 1:
                time.sleep(RETRY_DELAY)
            else:
                print(f"[ERROR] {e}")
    return None


print("")
print("=" * 70)
print("EnGenius Switch Extender Export")
print(f"Timestamp: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}")
print("=" * 70)

# Get orgs
print("\n[INFO] Fetching organizations...")
orgs = api_get("/user/orgs")
if not orgs:
    print("[ERROR] Could not get organizations")
    sys.exit(1)

if isinstance(orgs, dict):
    orgs = [orgs]

print(f"[INFO] Found {len(orgs)} organization(s)")

all_extenders = []

for org in orgs:
    org_id = org.get("id") or org.get("_id")
    org_name = org.get("name", "Unknown")
    print(f"\n[INFO] Organization: {org_name}")
    print(f"[INFO] Querying inventory for type=switch_extender...")

    result = api_get(f"/orgs/{org_id}/inventory", params={"type": "switch_extender", "count": 1000})

    if not result:
        print("[WARN] No results from inventory query")
        continue

    devices = result.get("devices", []) if isinstance(result, dict) else result
    api_size = result.get("size", len(devices)) if isinstance(result, dict) else len(devices)

    print(f"[INFO] API reports {api_size} switch extender(s), returned {len(devices)}")

    for dev in devices:
        # Parse expiration
        expired_date = dev.get("expired_date")
        exp_str = ""
        days_left = ""
        if expired_date:
            try:
                exp_dt = datetime.fromtimestamp(expired_date / 1000)
                exp_str = exp_dt.strftime("%Y-%m-%d")
                delta = exp_dt - datetime.now()
                days_left = str(delta.days)
            except:
                pass

        ext = {
            "organization": org_name,
            "network": dev.get("network_name", ""),
            "name": dev.get("name", ""),
            "model": dev.get("model", ""),
            "mac": dev.get("mac", ""),
            "serial_number": dev.get("serial_number", ""),
            "license_status": dev.get("license_status", ""),
            "license_type": dev.get("license_type", ""),
            "expiration_date": exp_str,
            "days_until_expiration": days_left,
            "registered_by": dev.get("registered_by", ""),
        }
        all_extenders.append(ext)

        print(f"  {ext['name']}")
        print(f"    Model:     {ext['model']}")
        print(f"    MAC:       {ext['mac']}")
        print(f"    Serial:    {ext['serial_number']}")
        print(f"    Network:   {ext['network']}")
        print(f"    License:   {ext['license_status']} (expires {ext['expiration_date']}, {ext['days_until_expiration']}d)")
        print("")

# Summary
print("=" * 70)
print(f"TOTAL: {len(all_extenders)} switch extender(s)")
print("=" * 70)

if not all_extenders:
    print("\nNo switch extenders found.")
    sys.exit(0)

# Export CSV
ts = datetime.now().strftime("%Y%m%d_%H%M%S")
filename = f"engenius_switch_extenders_{ts}.csv"

fields = [
    "organization", "network", "name", "model", "mac", "serial_number",
    "license_status", "license_type", "expiration_date", "days_until_expiration",
    "registered_by"
]

with open(filename, "w", newline="") as f:
    writer = csv.DictWriter(f, fieldnames=fields)
    writer.writeheader()
    writer.writerows(all_extenders)

print(f"\n[INFO] Exported: {filename}")
