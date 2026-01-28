#!/usr/bin/env python3
"""
EnGenius Cloud Site WAN IP Export
Gets WAN IP for each site and enriches with city, state, ISP info

Usage:
    1. Put your API key in api_key.txt (same directory)
    2. Run: python3 engenius_site_wan_export.py
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

# License status cache (MAC -> license_status)
license_cache = {}

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
                    time.sleep(RETRY_DELAY)
                    continue
                else:
                    return None
            else:
                return None
        except Exception as e:
            if attempt < MAX_RETRIES - 1:
                time.sleep(RETRY_DELAY)
            else:
                return None
    return None

def get_ip_info(ip):
    """Get city, state, ISP from IP address using ipinfo.io"""
    if not ip or ip in ["", "N/A", None]:
        return {"city": "", "state": "", "isp": ""}
    
    try:
        # ipinfo.io - free tier, no API key needed for basic info
        resp = requests.get(f"https://ipinfo.io/{ip}/json", timeout=10)
        if resp.status_code == 200:
            data = resp.json()
            # ipinfo returns region for state, org for ISP
            return {
                "city": data.get("city", ""),
                "state": data.get("region", ""),
                "isp": data.get("org", "")
            }
    except Exception as e:
        print(f"[ERR: {e}]", end=" ")
    
    return {"city": "", "state": "", "isp": ""}

# =============================================================================
# MAIN
# =============================================================================
print("=" * 70)
print("EnGenius Cloud Site WAN IP Export")
print("=" * 70)

all_sites = []
seen_networks = {}  # Track unique networks to avoid duplicates

# Get organizations
print("\n[1] Getting organizations...")
orgs = api_get("/user/orgs")
if not orgs:
    print("ERROR: Could not get organizations")
    sys.exit(1)

if isinstance(orgs, dict):
    orgs = [orgs]

print(f"    Found {len(orgs)} organization(s)")

# First, build license cache from inventory
print("\n[2] Building license cache from inventory...")
for org in orgs:
    org_id = org.get("id") or org.get("_id")
    org_name = org.get("name", "Unknown")
    
    inventory = api_get(f"/orgs/{org_id}/inventory", params={"count": 1000})
    if inventory:
        devices = inventory.get("devices", []) if isinstance(inventory, dict) else inventory
        for device in devices:
            mac = device.get("mac", "").lower()
            if mac:
                license_cache[mac] = {
                    "status": device.get("license_status", "unknown"),
                    "expired_date": device.get("expired_date")
                }
    print(f"    [{org_name}] Cached {len(license_cache)} devices")

print(f"    Total devices in license cache: {len(license_cache)}")

print("\n[3] Scanning networks for WAN IPs...")

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
            
            # Skip if we've already processed this network
            if net_id in seen_networks:
                continue
            seen_networks[net_id] = True
            
            print(f"    [NET] {net_name}...", end=" ", flush=True)
            
            wan_ip = None
            all_expired = ""
            total_switches = 0
            expired_switches = 0
            ap_list = []
            
            # Try to get WAN IP from switches first
            switches = api_get(f"/orgs/{org_id}/hvs/{hv_id}/networks/{net_id}/devices/switches")
            if switches:
                if isinstance(switches, dict):
                    switch_list = switches.get("switches", switches.get("devices", []))
                else:
                    switch_list = switches
                
                total_switches = len(switch_list)
                
                # Check license status for each switch
                for switch in switch_list:
                    mac = switch.get("mac", "").lower()
                    license_info = license_cache.get(mac, {})
                    status = license_info.get("status", "unknown")
                    
                    if status == "expired":
                        expired_switches += 1
                    
                    # WAN IP is nested inside "information" object
                    if not wan_ip:
                        info = switch.get("information", {})
                        if isinstance(info, dict):
                            wan = info.get("wan_ip")
                            if wan and wan not in ["", "N/A", None, "0.0.0.0"]:
                                wan_ip = wan
                
                # Determine if all switches are expired
                if total_switches > 0 and expired_switches == total_switches:
                    all_expired = "YES - DATA MAY BE STALE"
                elif expired_switches > 0:
                    all_expired = f"PARTIAL ({expired_switches}/{total_switches} expired)"
            
            # If no WAN from switches, try APs
            if not wan_ip:
                aps = api_get(f"/orgs/{org_id}/hvs/{hv_id}/networks/{net_id}/devices/aps")
                if aps:
                    if isinstance(aps, dict):
                        ap_list = aps.get("aps", aps.get("devices", []))
                    else:
                        ap_list = aps
                    
                    for ap in ap_list:
                        # WAN IP is nested inside "information" object
                        info = ap.get("information", {})
                        if isinstance(info, dict):
                            wan = info.get("wan_ip")
                            if wan and wan not in ["", "N/A", None, "0.0.0.0"]:
                                wan_ip = wan
                                break
            
            if wan_ip:
                print(f"WAN: {wan_ip}", end="")
                if all_expired:
                    print(f" [{all_expired}]")
                else:
                    print()
            else:
                # More verbose "not found" message
                print(f"(no WAN IP) [switches: {total_switches}, APs: {len(ap_list)}]")
                wan_ip = ""
            
            all_sites.append({
                "organization": org_name,
                "hierarchy_view": hv_name,
                "network": net_name,
                "wan_ip": wan_ip,
                "city": "",
                "state": "",
                "isp": "",
                "all_expired": all_expired
            })

# =============================================================================
# ENRICH WITH IP GEOLOCATION
# =============================================================================
print("\n" + "=" * 70)
print("IP GEOLOCATION LOOKUP")
print("=" * 70)

unique_ips = set(s["wan_ip"] for s in all_sites if s["wan_ip"])
total_sites_with_ip = len([s for s in all_sites if s["wan_ip"]])
print(f"\n[4] Looking up {len(unique_ips)} unique WAN IPs (from {total_sites_with_ip} sites with IPs)...")

ip_cache = {}
for i, ip in enumerate(unique_ips):
    print(f"    [{i+1}/{len(unique_ips)}] {ip}...", end=" ", flush=True)
    info = get_ip_info(ip)
    ip_cache[ip] = info
    print(f"{info['city']}, {info['state']} - {info['isp']}")
    
    # Rate limit: ipinfo.io is generous, minimal delay
    if i < len(unique_ips) - 1:
        time.sleep(0.1)

# Apply cached info to all sites
for site in all_sites:
    if site["wan_ip"] in ip_cache:
        info = ip_cache[site["wan_ip"]]
        site["city"] = info["city"]
        site["state"] = info["state"]
        site["isp"] = info["isp"]

# =============================================================================
# EXPORT TO CSV
# =============================================================================
print("\n" + "=" * 70)
print("EXPORT")
print("=" * 70)

if not all_sites:
    print("No sites found!")
    sys.exit(1)

timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
filename = f"engenius_site_wan_{timestamp}.csv"

fieldnames = [
    "organization", "hierarchy_view", "network", "wan_ip", "city", "state", "isp", "all_expired"
]

with open(filename, "w", newline="") as f:
    writer = csv.DictWriter(f, fieldnames=fieldnames)
    writer.writeheader()
    writer.writerows(all_sites)

print(f"\n[+] Exported {len(all_sites)} sites to: {filename}")

# Summary
print(f"\nSummary:")
print(f"  Total Sites: {len(all_sites)}")
print(f"  Sites with WAN IP: {len([s for s in all_sites if s['wan_ip']])}")
print(f"  Unique WAN IPs: {len(unique_ips)}")

# ISP breakdown
isps = {}
for s in all_sites:
    isp = s["isp"] or "Unknown/No IP"
    isps[isp] = isps.get(isp, 0) + 1

print(f"\n  ISPs:")
for isp, count in sorted(isps.items(), key=lambda x: -x[1])[:10]:
    print(f"    {isp}: {count}")

# State breakdown
states = {}
for s in all_sites:
    state = s["state"] or "Unknown"
    states[state] = states.get(state, 0) + 1

print(f"\n  States:")
for state, count in sorted(states.items(), key=lambda x: -x[1])[:10]:
    print(f"    {state}: {count}")

# Expired status breakdown
all_exp_count = len([s for s in all_sites if "YES" in s["all_expired"]])
partial_exp_count = len([s for s in all_sites if "PARTIAL" in s["all_expired"]])
if all_exp_count or partial_exp_count:
    print(f"\n  ⚠️  License Status:")
    if all_exp_count:
        print(f"    Sites with ALL devices expired: {all_exp_count}")
    if partial_exp_count:
        print(f"    Sites with SOME devices expired: {partial_exp_count}")

print(f"\n[+] Done!")
