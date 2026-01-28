# enGenius_MSP_NetTools

Python scripts to export SSIDs, APs, switches, VLANs, and licenses from EnGenius Cloud to CSV.

## Requirements

- Python 3.6+
- `requests` library

```bash
pip install requests
```

## Setup

1. **Get your API key from EnGenius Cloud:**
   - Log in to [cloud.engenius.ai](https://cloud.engenius.ai)
   - Click your avatar (top right) → API Key → Generate new API key

2. **Create `api_key.txt`** in the same directory as the scripts:
   ```bash
   echo "YOUR_API_KEY_HERE" > api_key.txt
   ```

3. **Pro license required** - API access requires Pro feature plan

## Scripts

### engenius_ssid_export.py

Exports all SSID/WiFi configurations across all networks.

```bash
python3 engenius_ssid_export.py
```

**Output:** `engenius_ssids_TIMESTAMP.csv`

**Columns:** organization, hierarchy_view, network, ssid_name, ssid_id, enabled, vlan_id, auth_type, hidden, client_isolation, band_2_4g, band_5g, band_6g

---

### engenius_ap_export.py

Exports all wireless access point (WAP) inventory across all networks.

```bash
python3 engenius_ap_export.py
```

**Output:** `engenius_aps_TIMESTAMP.csv`

**Columns:** organization, hierarchy_view, network, ap_name, ap_id, model, mac, serial_number

---

### engenius_switch_vlan_export.py

Exports all switches and VLAN configurations across all networks.

```bash
python3 engenius_switch_vlan_export.py
```

**Output:** `engenius_switches_TIMESTAMP.csv`

**Columns:** organization, hierarchy_view, network, switch_name, switch_id, model, mac, serial_number

**Output:** `engenius_vlans_TIMESTAMP.csv`

**Columns:** organization, hierarchy_view, network, vlan_id, vlan_name

---

### engenius_license_export.py

Exports all device license information, sorted by expiration date (expired/expiring first).

```bash
python3 engenius_license_export.py
```

**Output:** `engenius_licenses_TIMESTAMP.csv`

**Columns:** organization, network_name, device_name, device_type, model, mac, serial_number, license_status, expiration_date, days_until_expiration

---

## API Reference

- **Documentation:** https://liveapi-console-dev.s3-us-west-2.amazonaws.com/engenius_cloud/falcon.html
- **Base URL:** `https://falcon.production.engenius.ai/v2`
- **Auth Header:** `api-key: YOUR_KEY`
- **Official Examples:** https://github.com/EnGenius-Cloud-Team/restful-api-example

## Troubleshooting

| Error | Solution |
|-------|----------|
| "API Key Is Invalid" | Check `api_key.txt` has no extra whitespace, regenerate key if needed |
| "402 Payment Required" | API requires Pro license on your organization |
| Many 503 errors | EnGenius API temporarily unavailable, scripts retry 3x automatically |
