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


def load_api_key():
    for f in ["api_key.txt", "apikey.txt", "API_KEY.txt"]:
        p = os.path.join(SCRIPT_DIR, f)
        if os.path.exists(p):
            key = open(p).read().strip().strip('"').strip("'")
            print(f"  Key: {key[:8]}...{key[-4:]} ({len(key)} chars) from {f}")
            return key
    print("ERROR: No api_key.txt found"); sys.exit(1)


# Module-level session, same pattern as working scripts
API_KEY = load_api_key()
session = requests.Session()
session.headers.update({
    "api-key": API_KEY,
    "Content-Type": "application/json",
    "Accept": "application/json"
})


def api_get(endpoint, params=None):
    """Matches the working script's api_get signature exactly."""
    url = f"{BASE_URL}{endpoint}"
    for attempt in range(MAX_RETRIES):
        try:
            if DEBUG: print(f"    [DEBUG] GET {url} params={params}")
            resp = session.get(url, params=params, timeout=30)
            if DEBUG: print(f"    [DEBUG] {resp.status_code}: {resp.text[:500]}")
            if resp.status_code == 200:
                return resp.json()
            if resp.status_code == 503 and attempt < MAX_RETRIES - 1:
                print(f"    [WARN] 503, retry {attempt+1}/{MAX_RETRIES}...")
                time.sleep(RETRY_DELAY); continue
            print(f"    [{resp.status_code}] {endpoint}: {resp.text[:200]}")
            return None
        except Exception as e:
            if attempt < MAX_RETRIES - 1:
                time.sleep(RETRY_DELAY)
            else:
                print(f"    [ERROR] {e}")
    return None


def short_date(val):
    """Parse expired_date (ms timestamp, int, or string) -> M/D/YYYY."""
    if not val: return ""
    if isinstance(val, (int, float)):
        try:
            dt = datetime.fromtimestamp(val / 1000)
            return f"{dt.month}/{dt.day}/{dt.year}"
        except: return str(val)
    for fmt in ("%Y-%m-%dT%H:%M:%S", "%Y-%m-%dT%H:%M:%SZ", "%Y-%m-%d"):
        try:
            dt = datetime.strptime(str(val).split(".")[0], fmt)
            return f"{dt.month}/{dt.day}/{dt.year}"
        except: continue
    return str(val)


def lic_status(exp_str):
    if not exp_str: return "", "No License"
    for fmt in ("%m/%d/%Y", "%Y-%m-%d"):
        try:
            days = (datetime.strptime(exp_str, fmt).date() - datetime.now().date()).days
            if days < 0: return days, "EXPIRED"
            if days <= 30: return days, "EXPIRING SOON"
            return days, "Active"
        except: continue
    return "", "Unknown"


def dev_status(device):
    info = device.get("information", {})
    if not isinstance(info, dict): info = {}
    s = info.get("status", device.get("status", "unknown"))
    if isinstance(s, (int, float)): return "Online" if s == 1 else "Offline"
    if isinstance(s, str):
        sl = s.lower()
        if sl in ("online", "1", "connected"): return "Online"
        if sl in ("offline", "0", "disconnected"): return "Offline"
    return str(s).capitalize() if s else "Unknown"


def dev_ip(device):
    info = device.get("information", {})
    if not isinstance(info, dict): info = {}
    return info.get("wan_ip", "") or info.get("ip", "") or device.get("ip", "")


AP_COLS = ["network", "device_name", "model", "mac", "ip", "status",
           "license_expiration", "days_until_expiration", "license_status"]
SW_COLS = ["network", "device_name", "device_type", "model", "mac", "ip", "status",
           "license_expiration", "days_until_expiration", "license_status"]


def main():
    print("EnGenius Cloud - Device & License Export")
    print("=" * 60)

    orgs = api_get("/user/orgs")
    if not orgs: print("[FATAL] Cannot reach API"); sys.exit(1)
    if isinstance(orgs, dict): orgs = [orgs]
    print(f"[OK] {len(orgs)} org(s)\n")

    state_data = {}
    net_to_hv = {}

    for org in orgs:
        org_id = org.get("id") or org.get("_id")
        org_name = org.get("name", "Unknown")
        print(f"[ORG] {org_name}")

        hvs = api_get(f"/orgs/{org_id}/hvs")
        if not hvs: continue
        if isinstance(hvs, dict): hvs = [hvs]

        for hv in hvs:
            hv_id = hv.get("id") or hv.get("_id")
            hv_name = hv.get("name", "root")
            networks = hv.get("networks", [])
            if not networks:
                nd = api_get(f"/orgs/{org_id}/hvs/{hv_id}/networks")
                if nd: networks = nd if isinstance(nd, list) else nd.get("networks", [])

            print(f"\n  [HV] {hv_name} ({len(networks)} networks)")
            if hv_name not in state_data: state_data[hv_name] = {"aps": [], "switches": []}

            for net in networks:
                net_to_hv[net.get("name", "")] = hv_name

            for net in networks:
                net_id = net.get("id") or net.get("_id")
                net_name = net.get("name", "Unknown")
                print(f"    {net_name}", end="")
                ac, sc = 0, 0

                # APs
                resp = api_get(f"/orgs/{org_id}/hvs/{hv_id}/networks/{net_id}/devices/aps", params={"count": 500})
                if resp:
                    for ap in (resp.get("aps", resp.get("devices", [])) if isinstance(resp, dict) else resp):
                        exp = short_date(ap.get("expired_date"))
                        days, stat = lic_status(exp)
                        state_data[hv_name]["aps"].append({
                            "network": net_name, "device_name": ap.get("name", ""),
                            "model": ap.get("model", ""), "mac": ap.get("mac", ""),
                            "ip": dev_ip(ap), "status": dev_status(ap),
                            "license_expiration": exp,
                            "days_until_expiration": days if days != "" else "",
                            "license_status": stat
                        })
                        ac += 1

                # Switches
                resp = api_get(f"/orgs/{org_id}/hvs/{hv_id}/networks/{net_id}/devices/switches", params={"count": 500})
                if resp:
                    for sw in (resp.get("switches", resp.get("devices", [])) if isinstance(resp, dict) else resp):
                        exp = short_date(sw.get("expired_date"))
                        days, stat = lic_status(exp)
                        state_data[hv_name]["switches"].append({
                            "network": net_name, "device_name": sw.get("name", ""),
                            "device_type": "Switch", "model": sw.get("model", ""),
                            "mac": sw.get("mac", ""), "ip": dev_ip(sw),
                            "status": dev_status(sw), "license_expiration": exp,
                            "days_until_expiration": days if days != "" else "",
                            "license_status": stat
                        })
                        sc += 1

                print(f" -> {ac} APs, {sc} switches")

        # ── Switch Extenders ──────────────────────────────────────────
        # Copied from working engenius_switch_extender_export.py
        print(f"\n  [INFO] Querying inventory for type=switch_extender...")
        result = api_get(f"/orgs/{org_id}/inventory", params={"type": "switch_extender", "count": 1000})

        if not result:
            print("  [WARN] No results from inventory query")
        else:
            devices = result.get("devices", []) if isinstance(result, dict) else result
            api_size = result.get("size", len(devices)) if isinstance(result, dict) else len(devices)
            print(f"  [INFO] API reports {api_size} switch extender(s), returned {len(devices)}")

            if DEBUG and devices:
                print(f"  [DEBUG] Extender keys: {list(devices[0].keys())}")
                print(f"  [DEBUG] Sample: {json.dumps(devices[0], indent=2, default=str)[:500]}")

            for dev in devices:
                # Parse expiration exactly like working script
                expired_date = dev.get("expired_date")
                exp_str = ""
                days_left = ""
                if expired_date:
                    try:
                        exp_dt = datetime.fromtimestamp(expired_date / 1000)
                        exp_str = f"{exp_dt.month}/{exp_dt.day}/{exp_dt.year}"
                        delta = exp_dt - datetime.now()
                        days_left = delta.days
                    except:
                        pass

                if days_left != "":
                    if days_left < 0: stat = "EXPIRED"
                    elif days_left <= 30: stat = "EXPIRING SOON"
                    else: stat = "Active"
                else:
                    stat = "No License"

                # Place into correct state
                ext_net = dev.get("network_name", "")
                ext_hv = net_to_hv.get(ext_net, "")
                if not ext_hv:
                    ext_hv = list(state_data.keys())[0] if state_data else "Unknown"
                if ext_hv not in state_data:
                    state_data[ext_hv] = {"aps": [], "switches": []}

                state_data[ext_hv]["switches"].append({
                    "network": ext_net,
                    "device_name": dev.get("name", ""),
                    "device_type": "Switch Extender",
                    "model": dev.get("model", ""),
                    "mac": dev.get("mac", ""),
                    "ip": "",
                    "status": "N/A",
                    "license_expiration": exp_str,
                    "days_until_expiration": days_left if days_left != "" else "",
                    "license_status": stat
                })
                print(f"    + {dev.get('name', '?')} ({dev.get('model', '?')}) -> {ext_hv}")

    # ─── Write CSVs ──────────────────────────────────────────────────────
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

    print(f"\n{'='*60}\nSUMMARY\n{'='*60}")
    for state, data in state_data.items():
        all_d = data["aps"] + data["switches"]
        if not all_d: continue
        exp = sum(1 for d in all_d if d["license_status"] == "EXPIRED")
        soon = sum(1 for d in all_d if d["license_status"] == "EXPIRING SOON")
        ok = sum(1 for d in all_d if d["license_status"] == "Active")
        ext = sum(1 for d in data["switches"] if d.get("device_type") == "Switch Extender")
        sw = len(data["switches"]) - ext
        print(f"  {state}: {len(data['aps'])} APs, {sw} switches, {ext} extenders ({ok} active, {soon} expiring, {exp} expired)")
    print(f"\nOutput: {out}/")


if __name__ == "__main__":
    main()
