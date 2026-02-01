#!/usr/bin/env python3
"""
EnGenius Cloud SSID Export
Exports SSID info from all networks to CSV

Usage:
    1. Put your API key in api_key.txt (same directory)
    2. Run: python3 engenius_ssid_export.py
"""

import requests
import json
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
RETRY_DELAY = 2  # seconds

# Read API key from file
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
    """Make GET request with retry logic for 503 errors"""
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
                    print(f"[503 FAIL]", end=" ")
                    return None
            else:
                print(f"[{resp.status_code}]", end=" ")
                return None
        except Exception as e:
            print(f"[ERR]", end=" ")
            if attempt < MAX_RETRIES - 1:
                time.sleep(RETRY_DELAY)
            else:
                return None
    return None

# =============================================================================
# MAIN
# =============================================================================
print("=" * 70)
print("EnGenius Cloud SSID Export")
print("=" * 70)

# Collect all SSID data
all_ssids = []

# Step 1: Get organizations
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
    
    # Step 2: Get hierarchy views
    hvs = api_get(f"/orgs/{org_id}/hvs")
    if not hvs:
        continue
    
    if isinstance(hvs, dict):
        hvs = [hvs]
    
    for hv in hvs:
        hv_id = hv.get("id") or hv.get("_id")
        hv_name = hv.get("name", "root")
        
        # Get networks from HV
        networks = hv.get("networks", [])
        print(f"  [HV] {hv_name} - {len(networks)} network(s)")
        
        for network in networks:
            net_id = network.get("id") or network.get("_id")
            net_name = network.get("name", "Unknown")
            print(f"    [NET] {net_name}...", end=" ", flush=True)
            
            # Get SSIDs
            ssids = api_get(f"/orgs/{org_id}/hvs/{hv_id}/networks/{net_id}/policy/aps/ssid-profiles", params={"count": 500})
            
            if not ssids:
                print("(no data)")
                continue
            
            if isinstance(ssids, dict):
                ssids = [ssids]
            
            print(f"({len(ssids)} SSIDs)")
            
            for ssid in ssids:
                security = ssid.get("security", {})
                auth_type = security.get("auth_type", "unknown") if isinstance(security, dict) else "unknown"
                
                # Get VLAN - check multiple possible fields
                vlan_id = ssid.get("vlan_id")
                if vlan_id is None:
                    vlan_id = ssid.get("default_vlan_id", "")
                
                all_ssids.append({
                    "organization": org_name,
                    "hierarchy_view": hv_name,
                    "network": net_name,
                    "ssid_name": ssid.get("ssid_name", ""),
                    "ssid_id": ssid.get("id", ""),
                    "enabled": ssid.get("is_enable", ""),
                    "vlan_id": vlan_id if vlan_id else "",
                    "auth_type": auth_type,
                    "hidden": ssid.get("is_hidden", ""),
                    "client_isolation": ssid.get("is_client_isolation", ""),
                    "band_2_4g": next((t.get("is_enable") for t in ssid.get("ssid_types", []) if t.get("type") == "2_4G"), ""),
                    "band_5g": next((t.get("is_enable") for t in ssid.get("ssid_types", []) if t.get("type") == "5G"), ""),
                    "band_6g": next((t.get("is_enable") for t in ssid.get("ssid_types", []) if t.get("type") == "6G"), ""),
                })

# =============================================================================
# EXPORT TO CSV
# =============================================================================
print("\n" + "=" * 70)
print("EXPORT")
print("=" * 70)

if not all_ssids:
    print("No SSIDs found to export!")
    sys.exit(1)

# Generate filename with timestamp
timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
filename = f"engenius_ssids_{timestamp}.csv"

# Write CSV
fieldnames = [
    "organization", "hierarchy_view", "network", "ssid_name", "ssid_id",
    "enabled", "vlan_id", "auth_type", "hidden", "client_isolation",
    "band_2_4g", "band_5g", "band_6g"
]

with open(filename, "w", newline="") as f:
    writer = csv.DictWriter(f, fieldnames=fieldnames)
    writer.writeheader()
    writer.writerows(all_ssids)

print(f"\n[+] Exported {len(all_ssids)} SSIDs to: {filename}")

# Print summary
print(f"\nSummary:")
print(f"  Total SSIDs: {len(all_ssids)}")
print(f"  Networks with SSIDs: {len(set(s['network'] for s in all_ssids))}")

# Show unique auth types
auth_types = {}
for s in all_ssids:
    auth = s["auth_type"]
    auth_types[auth] = auth_types.get(auth, 0) + 1

print(f"\n  Auth Types:")
for auth, count in sorted(auth_types.items(), key=lambda x: -x[1]):
    print(f"    {auth}: {count}")

print(f"\n[+] Done!")
