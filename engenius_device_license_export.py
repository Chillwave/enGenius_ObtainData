#!/usr/bin/env python3
"""
EnGenius Cloud - Device & License Export by State
Output: per-state CSVs (State - Wireless APs.csv, State - Switches.csv)
Usage:  python3 engenius_device_license_export.py [--debug]
"""
import sys, os, csv, json, time, requests
from datetime import datetime

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

BASE_URL = "https://falcon.production.engenius.ai/v2"
MAX_RETRIES = 3
RETRY_DELAY = 5
DEBUG = "--debug" in sys.argv
SCRIPT_DIR = os.path.dirname(os.path.abspath(__file__))


# ─── API ─────────────────────────────────────────────────────────────────────

def load_api_key():
    path = os.path.join(SCRIPT_DIR, "api_key.txt")
    if not os.path.exists(path):
        print(f"ERROR: {path} not found"); sys.exit(1)
    key = open(path).read().strip().strip('"').strip("'")
    print(f"  Key: {key[:8]}...{key[-4:]} ({len(key)} chars)")
    return key


def api_get(session, endpoint, params=None):
    url = f"{BASE_URL}{endpoint}"
    for attempt in range(MAX_RETRIES):
        try:
            if DEBUG: print(f"    [DEBUG] GET {url}")
            resp = session.get(url, params=params, timeout=30)
            if DEBUG: print(f"    [DEBUG] {resp.status_code}: {resp.text[:500]}")
            if resp.status_code == 200: return resp.json()
            if resp.status_code == 503 and attempt < MAX_RETRIES - 1:
                time.sleep(RETRY_DELAY); continue
            print(f"    [{resp.status_code}] {endpoint}: {resp.text[:200]}")
            return None
        except Exception as e:
            if attempt < MAX_RETRIES - 1: time.sleep(RETRY_DELAY)
            else: print(f"    [ERROR] {e}")
    return None


# ─── Helpers ─────────────────────────────────────────────────────────────────

def parse_expiration(val):
    """Parse expired_date from int timestamp or string -> YYYY-MM-DD."""
    if not val: return ""
    if isinstance(val, (int, float)):
        try:
            ts = val / 1000 if val > 1e12 else val
            return datetime.fromtimestamp(ts).strftime("%Y-%m-%d")
        except: return str(val)
    for fmt in ("%Y-%m-%dT%H:%M:%S", "%Y-%m-%dT%H:%M:%SZ", "%Y-%m-%d"):
        try: return datetime.strptime(str(val).split(".")[0], fmt).strftime("%Y-%m-%d")
        except: continue
    return str(val)


def license_status(exp_str):
    if not exp_str: return "", "No License"
    try: days = (datetime.strptime(exp_str, "%Y-%m-%d").date() - datetime.now().date()).days
    except: return "", "Unknown"
    if days < 0: return days, "EXPIRED"
    if days <= 30: return days, "EXPIRING SOON"
    return days, "Active"


def device_status(device):
    info = device.get("information", {})
    if not isinstance(info, dict): info = {}
    s = info.get("status", device.get("status", "unknown"))
    if isinstance(s, (int, float)): return "Online" if s == 1 else "Offline"
    if isinstance(s, str):
        sl = s.lower()
        if sl in ("online", "1", "connected"): return "Online"
        if sl in ("offline", "0", "disconnected"): return "Offline"
    return str(s).capitalize() if s else "Unknown"


def device_ip(device):
    info = device.get("information", {})
    if not isinstance(info, dict): info = {}
    return info.get("wan_ip", "") or info.get("ip", "") or device.get("ip", "")


# ─── Main ────────────────────────────────────────────────────────────────────

AP_COLS = ["organization", "hierarchy_view", "network", "device_name", "model",
           "mac", "ip", "status", "license_expiration", "days_until_expiration", "license_status"]
SW_COLS = ["organization", "hierarchy_view", "network", "device_name", "device_type", "model",
           "mac", "ip", "status", "license_expiration", "days_until_expiration", "license_status"]


def main():
    print("EnGenius Cloud - Device & License Export")
    print("=" * 60)

    api_key = load_api_key()
    session = requests.Session()
    session.headers.update({"api-key": api_key, "Content-Type": "application/json", "Accept": "application/json"})

    orgs = api_get(session, "/user/orgs")
    if not orgs: print("[FATAL] Cannot reach API"); sys.exit(1)
    if isinstance(orgs, dict): orgs = [orgs]
    print(f"[OK] {len(orgs)} org(s)\n")

    state_data = {}  # hv_name -> {"aps": [], "switches": []}

    for org in orgs:
        org_id = org.get("id") or org.get("_id")
        org_name = org.get("name", "Unknown")
        print(f"[ORG] {org_name}")

        hvs = api_get(session, f"/orgs/{org_id}/hvs")
        if not hvs: continue
        if isinstance(hvs, dict): hvs = [hvs]

        for hv in hvs:
            hv_id = hv.get("id") or hv.get("_id")
            hv_name = hv.get("name", "root")
            networks = hv.get("networks", [])
            if not networks:
                nd = api_get(session, f"/orgs/{org_id}/hvs/{hv_id}/networks")
                if nd: networks = nd if isinstance(nd, list) else nd.get("networks", [])

            print(f"\n  [HV] {hv_name} ({len(networks)} networks)")
            if hv_name not in state_data: state_data[hv_name] = {"aps": [], "switches": []}

            for net in networks:
                net_id = net.get("id") or net.get("_id")
                net_name = net.get("name", "Unknown")
                print(f"    {net_name}", end="")
                ac, sc = 0, 0

                # APs
                resp = api_get(session, f"/orgs/{org_id}/hvs/{hv_id}/networks/{net_id}/devices/aps", {"count": 500})
                if resp:
                    for ap in (resp.get("aps", resp.get("devices", [])) if isinstance(resp, dict) else resp):
                        exp = parse_expiration(ap.get("expired_date", ""))
                        days, stat = license_status(exp)
                        state_data[hv_name]["aps"].append({
                            "organization": org_name, "hierarchy_view": hv_name, "network": net_name,
                            "device_name": ap.get("name", ""), "model": ap.get("model", ""),
                            "mac": ap.get("mac", ""), "ip": device_ip(ap), "status": device_status(ap),
                            "license_expiration": exp, "days_until_expiration": days if days != "" else "",
                            "license_status": stat
                        })
                        ac += 1

                # Switches
                resp = api_get(session, f"/orgs/{org_id}/hvs/{hv_id}/networks/{net_id}/devices/switches", {"count": 500})
                if resp:
                    for sw in (resp.get("switches", resp.get("devices", [])) if isinstance(resp, dict) else resp):
                        exp = parse_expiration(sw.get("expired_date", ""))
                        days, stat = license_status(exp)
                        state_data[hv_name]["switches"].append({
                            "organization": org_name, "hierarchy_view": hv_name, "network": net_name,
                            "device_name": sw.get("name", ""), "device_type": "Switch",
                            "model": sw.get("model", ""), "mac": sw.get("mac", ""),
                            "ip": device_ip(sw), "status": device_status(sw),
                            "license_expiration": exp, "days_until_expiration": days if days != "" else "",
                            "license_status": stat
                        })
                        sc += 1

                print(f" -> {ac} APs, {sc} switches")

        # Switch extenders (inventory only, no /devices/ endpoint)
        ext_resp = api_get(session, f"/orgs/{org_id}/inventory/devices", {"type": "switch_extender"})
        if ext_resp:
            ext_list = ext_resp if isinstance(ext_resp, list) else ext_resp.get("devices", ext_resp.get("data", []))
            if ext_list:
                print(f"\n  [EXTENDERS] {len(ext_list)} switch extender(s)")
                for ext in ext_list:
                    ext_hv = ext.get("hv_name", "") or (list(state_data.keys())[0] if state_data else "Unknown")
                    if ext_hv not in state_data: state_data[ext_hv] = {"aps": [], "switches": []}
                    exp = parse_expiration(ext.get("expired_date") or ext.get("expiration_date", ""))
                    days, stat = license_status(exp)
                    state_data[ext_hv]["switches"].append({
                        "organization": org_name, "hierarchy_view": ext_hv,
                        "network": ext.get("network_name", ""),
                        "device_name": ext.get("name", ""), "device_type": "Switch Extender",
                        "model": ext.get("model", ""), "mac": ext.get("mac", ""),
                        "ip": ext.get("ip", ""), "status": device_status(ext),
                        "license_expiration": exp, "days_until_expiration": days if days != "" else "",
                        "license_status": stat
                    })

    # ─── Write CSVs ──────────────────────────────────────────────────────────
    if not any(d["aps"] or d["switches"] for d in state_data.values()):
        print("\n[WARN] No devices found."); sys.exit(1)

    out = os.path.join(SCRIPT_DIR, f"engenius_export_{datetime.now().strftime('%Y%m%d_%H%M%S')}")
    os.makedirs(out, exist_ok=True)
    print(f"\n{'='*60}\nWRITING CSVs\n{'='*60}")

    sort_key = lambda x: x["days_until_expiration"] if isinstance(x["days_until_expiration"], int) else 99999

    for state, data in state_data.items():
        for label, rows, cols in [("Wireless APs", data["aps"], AP_COLS), ("Switches", data["switches"], SW_COLS)]:
            if not rows: continue
            rows.sort(key=sort_key)
            path = os.path.join(out, f"{state} - {label}.csv")
            with open(path, "w", newline="") as f:
                w = csv.DictWriter(f, fieldnames=cols); w.writeheader(); w.writerows(rows)
            print(f"  {state} - {label}: {len(rows)}")

    # Summary
    print(f"\n{'='*60}\nSUMMARY\n{'='*60}")
    for state, data in state_data.items():
        all_d = data["aps"] + data["switches"]
        if not all_d: continue
        exp = sum(1 for d in all_d if d["license_status"] == "EXPIRED")
        soon = sum(1 for d in all_d if d["license_status"] == "EXPIRING SOON")
        ok = sum(1 for d in all_d if d["license_status"] == "Active")
        print(f"  {state}: {len(data['aps'])} APs, {len(data['switches'])} switches ({ok} active, {soon} expiring, {exp} expired)")
    print(f"\nOutput: {out}/")


if __name__ == "__main__":
    main()
