#!/usr/bin/env python3
"""
EnGenius Cloud - Device & License Export by State
Exports devices with license expiration, split by state and device type.

Output files:
    Alabama - Wireless APs.csv
    Alabama - Switches.csv
    Florida - Wireless APs.csv
    ...

Usage:
    python3 engenius_device_license_export.py
    python3 engenius_device_license_export.py --debug

Requires:
    - api_key.txt in same directory
    - Pro feature plan on org
    - requests library
"""

import sys
import os
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))  # Windows compatibility fix

import csv
import json
import time
import requests
from datetime import datetime

# ─── Config ──────────────────────────────────────────────────────────────────

BASE_URL = "https://falcon.production.engenius.ai/v2"
MAX_RETRIES = 3
RETRY_DELAY = 5
DEBUG = "--debug" in sys.argv

# ─── API Client ──────────────────────────────────────────────────────────────

class EnGeniusAPI:
    def __init__(self, api_key):
        self.session = requests.Session()
        self.session.headers.update({
            "api-key": api_key,
            "Content-Type": "application/json",
            "Accept": "application/json"
        })

    def get(self, endpoint, params=None):
        url = f"{BASE_URL}{endpoint}"
        for attempt in range(MAX_RETRIES):
            try:
                if DEBUG:
                    print(f"    [DEBUG] GET {url}")
                    if params:
                        print(f"    [DEBUG] Params: {params}")

                resp = self.session.get(url, params=params, timeout=30)

                if DEBUG:
                    print(f"    [DEBUG] Status: {resp.status_code}")
                    print(f"    [DEBUG] Body: {resp.text[:500]}")

                if resp.status_code == 200:
                    return resp.json()
                elif resp.status_code == 406:
                    print(f"    [ERROR] 406: {endpoint} - {resp.text[:200]}")
                    return None
                elif resp.status_code == 402:
                    print(f"    [ERROR] 402 Pro license needed: {endpoint}")
                    return None
                elif resp.status_code == 503:
                    if attempt < MAX_RETRIES - 1:
                        print(f"    [WARN] 503 retry {attempt + 1}/{MAX_RETRIES}...")
                        time.sleep(RETRY_DELAY)
                        continue
                else:
                    print(f"    [WARN] HTTP {resp.status_code}: {endpoint} - {resp.text[:200]}")
                return None
            except Exception as e:
                if attempt < MAX_RETRIES - 1:
                    print(f"    [WARN] {e}, retry {attempt + 1}/{MAX_RETRIES}...")
                    time.sleep(RETRY_DELAY)
                else:
                    print(f"    [ERROR] Failed after {MAX_RETRIES} attempts: {e}")
        return None


# ─── Helpers ─────────────────────────────────────────────────────────────────

def load_api_key():
    script_dir = os.path.dirname(os.path.abspath(__file__))
    key_path = os.path.join(script_dir, "api_key.txt")
    if not os.path.exists(key_path):
        print(f"ERROR: {key_path} not found.")
        sys.exit(1)
    with open(key_path, "r") as f:
        key = f.read().strip().strip('"').strip("'")
    print(f"  API key: {key[:8]}...{key[-4:]} ({len(key)} chars)")
    return key


def parse_expiration(exp_raw):
    """Parse expiration from string or unix timestamp (ms or seconds). Returns date string."""
    if not exp_raw:
        return ""

    # Handle integer/float timestamps
    if isinstance(exp_raw, (int, float)):
        try:
            # If > 1e12, it's milliseconds
            ts = exp_raw / 1000 if exp_raw > 1e12 else exp_raw
            return datetime.fromtimestamp(ts).strftime("%Y-%m-%d")
        except (ValueError, OSError, OverflowError):
            return str(exp_raw)

    # Handle string
    exp_str = str(exp_raw)
    for fmt in ("%Y-%m-%dT%H:%M:%S", "%Y-%m-%dT%H:%M:%SZ", "%Y-%m-%d", "%m/%d/%Y"):
        try:
            return datetime.strptime(exp_str.split(".")[0], fmt).strftime("%Y-%m-%d")
        except (ValueError, AttributeError):
            continue

    return exp_str


def get_license_status(exp_display):
    """Get days remaining and status from a YYYY-MM-DD string."""
    if not exp_display:
        return None, "No License"
    try:
        exp_date = datetime.strptime(exp_display, "%Y-%m-%d").date()
    except (ValueError, TypeError):
        return None, "Unknown"

    days_left = (exp_date - datetime.now().date()).days
    if days_left < 0:
        return days_left, "EXPIRED"
    elif days_left <= 30:
        return days_left, "EXPIRING SOON"
    else:
        return days_left, "Active"


def parse_status(device):
    """Extract online/offline status from device data."""
    info = device.get("information", {})
    if not isinstance(info, dict):
        info = {}

    status = info.get("status", device.get("status", "unknown"))

    # Normalize to Online/Offline
    if isinstance(status, str):
        s = status.lower().strip()
        if s in ("online", "1", "connected", "active"):
            return "Online"
        elif s in ("offline", "0", "disconnected", "inactive"):
            return "Offline"
        return status.capitalize()
    elif isinstance(status, (int, float)):
        return "Online" if status == 1 else "Offline"

    return "Unknown"


# ─── Main Export ─────────────────────────────────────────────────────────────

AP_HEADERS = [
    "organization", "hierarchy_view", "network", "device_name",
    "model", "mac", "ip", "status",
    "license_expiration", "days_until_expiration", "license_status"
]

SW_HEADERS = [
    "organization", "hierarchy_view", "network", "device_name",
    "device_type", "model", "mac", "ip", "status",
    "license_expiration", "days_until_expiration", "license_status"
]


def main():
    print("EnGenius Cloud - Device & License Export")
    print("=" * 60)
    if DEBUG:
        print("[DEBUG MODE]\n")

    api_key = load_api_key()
    api = EnGeniusAPI(api_key)

    # ─── Connectivity test ────────────────────────────────────────────────
    print("\n[DIAG] Testing API connectivity...")
    orgs = api.get("/user/orgs")
    if not orgs:
        print("\n[FATAL] Cannot reach /user/orgs")
        print("  Check: API key, IP allowlist, Pro license, internet")
        sys.exit(1)

    if isinstance(orgs, dict):
        orgs = [orgs]
    print(f"[OK] Connected! Found {len(orgs)} organization(s)")

    # ─── Build license lookup from inventory ──────────────────────────────
    license_lookup = {}
    for org in orgs:
        org_id = org.get("id") or org.get("_id")
        for inv_endpoint in [
            f"/orgs/{org_id}/inventory/devices",
            f"/orgs/{org_id}/inventory",
        ]:
            inv_data = api.get(inv_endpoint)
            if inv_data:
                inv_list = inv_data if isinstance(inv_data, list) else inv_data.get("devices", inv_data.get("data", []))
                if DEBUG and inv_list:
                    print(f"  [DEBUG] Inventory keys: {list(inv_list[0].keys())}")
                    print(f"  [DEBUG] Sample: {json.dumps(inv_list[0], indent=2, default=str)[:500]}")
                for dev in inv_list:
                    serial = dev.get("serial_number") or dev.get("serialNumber") or ""
                    mac = dev.get("mac") or dev.get("mac_address") or ""
                    exp = (dev.get("license_expiration") or dev.get("licenseExpiration") or
                           dev.get("license_expired_at") or dev.get("expiration_date") or
                           dev.get("expired_date") or dev.get("expiredDate") or "")
                    if serial and exp:
                        license_lookup[serial] = exp
                    if mac and exp:
                        license_lookup[mac.upper()] = exp
                break

    print(f"[INFO] License lookup: {len(license_lookup)} records")

    # ─── Walk hierarchy ───────────────────────────────────────────────────
    timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
    script_dir = os.path.dirname(os.path.abspath(__file__))
    output_dir = os.path.join(script_dir, f"engenius_export_{timestamp}")
    os.makedirs(output_dir, exist_ok=True)

    # state_name -> {"aps": [...], "switches": [...]}
    state_data = {}
    total_aps = 0
    total_switches = 0

    for org in orgs:
        org_id = org.get("id") or org.get("_id")
        org_name = org.get("name", "Unknown")
        print(f"\n[ORG] {org_name}")

        hvs = api.get(f"/orgs/{org_id}/hvs")
        if not hvs:
            print("  [WARN] No hierarchy views")
            continue
        if isinstance(hvs, dict):
            hvs = [hvs]

        if DEBUG and hvs:
            print(f"  [DEBUG] HV keys: {list(hvs[0].keys())}")

        for hv in hvs:
            hv_id = hv.get("id") or hv.get("_id")
            hv_name = hv.get("name", "root")
            networks = hv.get("networks", [])

            print(f"\n  [HV] {hv_name} ({len(networks)} networks)")

            if hv_name not in state_data:
                state_data[hv_name] = {"aps": [], "switches": []}

            # Fallback: fetch networks if not nested
            if not networks:
                net_data = api.get(f"/orgs/{org_id}/hvs/{hv_id}/networks")
                if net_data:
                    networks = net_data if isinstance(net_data, list) else net_data.get("networks", net_data.get("data", []))

            for network in networks:
                net_id = network.get("id") or network.get("_id")
                net_name = network.get("name", "Unknown")
                print(f"    [NET] {net_name}", end="")

                ap_count = 0
                sw_count = 0

                # ──── APs ─────────────────────────────────────────────
                aps_resp = api.get(
                    f"/orgs/{org_id}/hvs/{hv_id}/networks/{net_id}/devices/aps",
                    params={"count": 500}
                )
                if aps_resp:
                    ap_list = aps_resp.get("aps", aps_resp.get("devices", [])) if isinstance(aps_resp, dict) else aps_resp

                    if DEBUG and ap_list:
                        print(f"\n    [DEBUG] AP keys: {list(ap_list[0].keys())}")
                        print(f"    [DEBUG] Sample AP: {json.dumps(ap_list[0], indent=2, default=str)[:500]}")

                    for ap in ap_list:
                        info = ap.get("information", {})
                        if not isinstance(info, dict):
                            info = {}

                        mac = ap.get("mac", "")
                        serial = ap.get("serial_number", "")

                        # License lookup
                        exp_raw = ""
                        if serial:
                            exp_raw = license_lookup.get(serial, "")
                        if not exp_raw and mac:
                            exp_raw = license_lookup.get(mac.upper(), "")

                        exp_display = parse_expiration(exp_raw)
                        days_left, lic_status = get_license_status(exp_display)

                        row = {
                            "organization": org_name,
                            "hierarchy_view": hv_name,
                            "network": net_name,
                            "device_name": ap.get("name", ""),
                            "model": ap.get("model", ""),
                            "mac": mac,
                            "ip": info.get("wan_ip", "") or info.get("ip", "") or ap.get("ip", ""),
                            "status": parse_status(ap),
                            "license_expiration": exp_display,
                            "days_until_expiration": days_left if days_left is not None else "",
                            "license_status": lic_status
                        }
                        state_data[hv_name]["aps"].append(row)
                        ap_count += 1

                # ──── Switches ────────────────────────────────────────
                sw_resp = api.get(
                    f"/orgs/{org_id}/hvs/{hv_id}/networks/{net_id}/devices/switches",
                    params={"count": 500}
                )
                if sw_resp:
                    sw_list = sw_resp.get("switches", sw_resp.get("devices", [])) if isinstance(sw_resp, dict) else sw_resp

                    if DEBUG and sw_list:
                        print(f"\n    [DEBUG] SW keys: {list(sw_list[0].keys())}")
                        print(f"    [DEBUG] Sample SW: {json.dumps(sw_list[0], indent=2, default=str)[:500]}")

                    for switch in sw_list:
                        info = switch.get("information", {})
                        if not isinstance(info, dict):
                            info = {}

                        mac = switch.get("mac", "")
                        serial = switch.get("serial_number", "")

                        exp_raw = ""
                        if serial:
                            exp_raw = license_lookup.get(serial, "")
                        if not exp_raw and mac:
                            exp_raw = license_lookup.get(mac.upper(), "")

                        exp_display = parse_expiration(exp_raw)
                        days_left, lic_status = get_license_status(exp_display)

                        row = {
                            "organization": org_name,
                            "hierarchy_view": hv_name,
                            "network": net_name,
                            "device_name": switch.get("name", ""),
                            "device_type": "Switch",
                            "model": switch.get("model", ""),
                            "mac": mac,
                            "ip": info.get("wan_ip", "") or info.get("ip", "") or switch.get("ip", ""),
                            "status": parse_status(switch),
                            "license_expiration": exp_display,
                            "days_until_expiration": days_left if days_left is not None else "",
                            "license_status": lic_status
                        }
                        state_data[hv_name]["switches"].append(row)
                        sw_count += 1

                # ──── Switch Extenders (inventory-based, no /devices/ endpoint) ──
                # Pulled once per org below, assigned to state by network match

                total_aps += ap_count
                total_switches += sw_count
                print(f" -> {ap_count} APs, {sw_count} switches")

        # ──── Switch Extenders from inventory ─────────────────────────────
        print(f"\n  [INFO] Fetching switch extenders from inventory...")
        ext_data = api.get(f"/orgs/{org_id}/inventory/devices", params={"type": "switch_extender"})
        ext_count = 0
        if ext_data:
            ext_list = ext_data if isinstance(ext_data, list) else ext_data.get("devices", ext_data.get("data", []))

            if DEBUG and ext_list:
                print(f"  [DEBUG] Extender keys: {list(ext_list[0].keys())}")
                print(f"  [DEBUG] Sample: {json.dumps(ext_list[0], indent=2, default=str)[:500]}")

            for ext in ext_list:
                mac = ext.get("mac") or ext.get("mac_address") or ""
                serial = ext.get("serial_number") or ext.get("serialNumber") or ""

                # Determine which HV/network this belongs to
                ext_network = ext.get("network_name") or ext.get("network", {}).get("name", "") if isinstance(ext.get("network"), dict) else ext.get("network", "")
                ext_hv = ext.get("hv_name") or ext.get("hierarchy_view", "")

                # If we can't determine HV, put in first available
                if not ext_hv:
                    if state_data:
                        ext_hv = list(state_data.keys())[0]
                    else:
                        ext_hv = "Unknown"

                if ext_hv not in state_data:
                    state_data[ext_hv] = {"aps": [], "switches": []}

                exp_raw = (ext.get("license_expiration") or ext.get("licenseExpiration") or
                           ext.get("license_expired_at") or ext.get("expiration_date") or
                           ext.get("expired_date") or ext.get("expiredDate") or "")
                if not exp_raw and serial:
                    exp_raw = license_lookup.get(serial, "")
                if not exp_raw and mac:
                    exp_raw = license_lookup.get(mac.upper(), "")

                exp_display = parse_expiration(exp_raw)
                days_left, lic_status = get_license_status(exp_display)

                row = {
                    "organization": org_name,
                    "hierarchy_view": ext_hv,
                    "network": ext_network if isinstance(ext_network, str) else "",
                    "device_name": ext.get("name") or ext.get("device_name") or "",
                    "device_type": "Switch Extender",
                    "model": ext.get("model") or ext.get("model_name") or "",
                    "mac": mac,
                    "ip": ext.get("ip") or ext.get("ip_address") or "",
                    "status": parse_status(ext),
                    "license_expiration": exp_display,
                    "days_until_expiration": days_left if days_left is not None else "",
                    "license_status": lic_status
                }
                state_data[ext_hv]["switches"].append(row)
                ext_count += 1
                total_switches += 1

        if ext_count:
            print(f"  [INFO] Added {ext_count} switch extender(s) to switch CSVs")

    # ─── Write CSVs ──────────────────────────────────────────────────────────

    if total_aps + total_switches == 0:
        print("\n[WARN] No devices found.")
        sys.exit(1)

    print(f"\n{'='*60}")
    print("WRITING CSVs")
    print(f"{'='*60}")

    files_written = 0

    for state_name, data in state_data.items():
        # APs CSV
        if data["aps"]:
            data["aps"].sort(key=lambda x: x["days_until_expiration"] if isinstance(x["days_until_expiration"], int) else 99999)
            safe_name = state_name.replace(" ", "_").replace("/", "_")
            filepath = os.path.join(output_dir, f"{state_name} - Wireless APs.csv")
            with open(filepath, "w", newline="") as f:
                writer = csv.DictWriter(f, fieldnames=AP_HEADERS)
                writer.writeheader()
                writer.writerows(data["aps"])
            print(f"  {state_name} - Wireless APs: {len(data['aps'])} devices")
            files_written += 1

        # Switches CSV (includes switch extenders)
        if data["switches"]:
            data["switches"].sort(key=lambda x: x["days_until_expiration"] if isinstance(x["days_until_expiration"], int) else 99999)
            filepath = os.path.join(output_dir, f"{state_name} - Switches.csv")
            with open(filepath, "w", newline="") as f:
                writer = csv.DictWriter(f, fieldnames=SW_HEADERS)
                writer.writeheader()
                writer.writerows(data["switches"])
            sw_regular = sum(1 for d in data["switches"] if d["device_type"] == "Switch")
            sw_ext = sum(1 for d in data["switches"] if d["device_type"] == "Switch Extender")
            print(f"  {state_name} - Switches: {sw_regular} switches, {sw_ext} extenders")
            files_written += 1

    # Summary
    print(f"\n{'='*60}")
    print("EXPORT SUMMARY")
    print(f"{'='*60}")
    print(f"Total APs: {total_aps}")
    print(f"Total Switches (incl extenders): {total_switches}")
    print(f"Files written: {files_written}")
    print(f"States: {len(state_data)}")
    for state_name, data in state_data.items():
        all_devs = data["aps"] + data["switches"]
        expired = sum(1 for d in all_devs if d["license_status"] == "EXPIRED")
        expiring = sum(1 for d in all_devs if d["license_status"] == "EXPIRING SOON")
        active = sum(1 for d in all_devs if d["license_status"] == "Active")
        no_lic = sum(1 for d in all_devs if d["license_status"] in ("No License", "Unknown"))
        parts = []
        if active: parts.append(f"{active} active")
        if expiring: parts.append(f"{expiring} expiring")
        if expired: parts.append(f"{expired} EXPIRED")
        if no_lic: parts.append(f"{no_lic} no license")
        print(f"  {state_name}: {len(data['aps'])} APs, {len(data['switches'])} switches ({', '.join(parts)})")
    print(f"\nOutput: {output_dir}/")


if __name__ == "__main__":
    main()
