#!/usr/bin/env python3
"""
EnGenius Cloud Switch & VLAN Export
Exports switch and VLAN info from all networks to CSV

Usage:
    1. Put your API key in api_key.txt (same directory)
    2. Run: python3 engenius_switch_vlan_export.py
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
print("EnGenius Cloud Switch & VLAN Export")
print("=" * 70)

# Collect all data
all_switches = []
all_vlans = []

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
            
            # =========================================================
            # GET SWITCHES
            # =========================================================
            print(f"    [NET] {net_name} - Switches...", end=" ", flush=True)
            
            switches = api_get(f"/orgs/{org_id}/hvs/{hv_id}/networks/{net_id}/devices/switches")
            
            if switches:
                if isinstance(switches, dict):
                    switch_list = switches.get("switches", [switches])
                else:
                    switch_list = switches
                
                print(f"({len(switch_list)} switches)", end=" ")
                
                for switch in switch_list:
                    all_switches.append({
                        "organization": org_name,
                        "hierarchy_view": hv_name,
                        "network": net_name,
                        "switch_name": switch.get("name", ""),
                        "switch_id": switch.get("id", ""),
                        "model": switch.get("model", ""),
                        "mac": switch.get("mac", ""),
                        "serial_number": switch.get("serial_number", ""),
                    })
            else:
                print("(no switches)", end=" ")
            
            # =========================================================
            # GET VLANs
            # =========================================================
            print("VLANs...", end=" ", flush=True)
            
            vlans = api_get(f"/orgs/{org_id}/hvs/{hv_id}/networks/{net_id}/policy/vlans")
            
            if vlans:
                # Response is {"vlans": [...]} or just a list
                if isinstance(vlans, dict):
                    vlan_list = vlans.get("vlans", [])
                else:
                    vlan_list = vlans
                
                print(f"({len(vlan_list)} VLANs)")
                
                for vlan in vlan_list:
                    all_vlans.append({
                        "organization": org_name,
                        "hierarchy_view": hv_name,
                        "network": net_name,
                        "vlan_id": vlan.get("id", ""),  # Field is 'id' not 'vlan_id'
                        "vlan_name": vlan.get("name", ""),
                    })
            else:
                print("(no VLANs)")

# =============================================================================
# EXPORT TO CSV
# =============================================================================
print("\n" + "=" * 70)
print("EXPORT")
print("=" * 70)

timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")

# Export Switches
if all_switches:
    switch_filename = f"engenius_switches_{timestamp}.csv"
    switch_fields = [
        "organization", "hierarchy_view", "network", "switch_name", "switch_id",
        "model", "mac", "serial_number"
    ]
    
    with open(switch_filename, "w", newline="") as f:
        writer = csv.DictWriter(f, fieldnames=switch_fields)
        writer.writeheader()
        writer.writerows(all_switches)
    
    print(f"\n[+] Exported {len(all_switches)} switches to: {switch_filename}")
else:
    print("\n[-] No switches found")

# Export VLANs
if all_vlans:
    vlan_filename = f"engenius_vlans_{timestamp}.csv"
    vlan_fields = [
        "organization", "hierarchy_view", "network", "vlan_id", "vlan_name"
    ]
    
    with open(vlan_filename, "w", newline="") as f:
        writer = csv.DictWriter(f, fieldnames=vlan_fields)
        writer.writeheader()
        writer.writerows(all_vlans)
    
    print(f"[+] Exported {len(all_vlans)} VLANs to: {vlan_filename}")
else:
    print("[-] No VLANs found")

# Print summary
print(f"\n" + "=" * 70)
print("SUMMARY")
print("=" * 70)
print(f"  Total Switches: {len(all_switches)}")
print(f"  Total VLANs: {len(all_vlans)}")
print(f"  Networks scanned: {len(set((s['network'] for s in all_switches + all_vlans)))}")

if all_switches:
    # Switch models breakdown
    models = {}
    for s in all_switches:
        m = s["model"] or "Unknown"
        models[m] = models.get(m, 0) + 1
    print(f"\n  Switch Models:")
    for model, count in sorted(models.items(), key=lambda x: -x[1]):
        print(f"    {model}: {count}")

print(f"\n[+] Done!")
