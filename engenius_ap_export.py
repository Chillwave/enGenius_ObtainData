#!/usr/bin/env python3
"""
EnGenius Cloud AP (WAP) Inventory Export
Exports all access point devices to CSV

Usage:
    1. Put your API key in api_key.txt (same directory)
    2. Run: python3 engenius_ap_export.py
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

# =============================================================================
# MAIN
# =============================================================================
print("=" * 70)
print("EnGenius Cloud AP (WAP) Inventory Export")
print("=" * 70)

all_aps = []

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
    
    # Get hierarchy views
    hvs = api_get(f"/orgs/{org_id}/hvs")
    if not hvs:
        continue
    
    if isinstance(hvs, dict):
        hvs = [hvs]
    
    for hv in hvs:
        hv_id = hv.get("id") or hv.get("_id")
        hv_name = hv.get("name", "root")
        
        networks = hv.get("networks", [])
        print(f"  [HV] {hv_name} - {len(networks)} network(s)")
        
        for network in networks:
            net_id = network.get("id") or network.get("_id")
            net_name = network.get("name", "Unknown")
            print(f"    [NET] {net_name}...", end=" ", flush=True)
            
            # Get APs
            aps = api_get(f"/orgs/{org_id}/hvs/{hv_id}/networks/{net_id}/devices/aps")
            
            if not aps:
                print("(no APs)")
                continue
            
            # Handle response format
            if isinstance(aps, dict):
                ap_list = aps.get("aps", aps.get("devices", []))
            else:
                ap_list = aps
            
            print(f"({len(ap_list)} APs)")
            
            for ap in ap_list:
                all_aps.append({
                    "organization": org_name,
                    "hierarchy_view": hv_name,
                    "network": net_name,
                    "ap_name": ap.get("name", ""),
                    "ap_id": ap.get("id", ""),
                    "model": ap.get("model", ""),
                    "mac": ap.get("mac", ""),
                    "serial_number": ap.get("serial_number", ""),
                })

# =============================================================================
# EXPORT TO CSV
# =============================================================================
print("\n" + "=" * 70)
print("EXPORT")
print("=" * 70)

if not all_aps:
    print("No APs found!")
    sys.exit(1)

timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
filename = f"engenius_aps_{timestamp}.csv"

fieldnames = [
    "organization", "hierarchy_view", "network", "ap_name", "ap_id",
    "model", "mac", "serial_number"
]

with open(filename, "w", newline="") as f:
    writer = csv.DictWriter(f, fieldnames=fieldnames)
    writer.writeheader()
    writer.writerows(all_aps)

print(f"\n[+] Exported {len(all_aps)} APs to: {filename}")

# Summary
print(f"\nSummary:")
print(f"  Total APs: {len(all_aps)}")
print(f"  Networks with APs: {len(set(a['network'] for a in all_aps))}")

# Model breakdown
models = {}
for a in all_aps:
    m = a["model"] or "Unknown"
    models[m] = models.get(m, 0) + 1

print(f"\n  AP Models:")
for model, count in sorted(models.items(), key=lambda x: -x[1]):
    print(f"    {model}: {count}")

print(f"\n[+] Done!")
