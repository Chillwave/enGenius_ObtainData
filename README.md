# enGenius_obtainData

Python scripts to export SSIDs, switches, VLANs, and licenses from EnGenius Cloud to CSV.

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

| Column | Description |
|--------|-------------|
| organization | Organization name |
| hierarchy_view | Hierarchy view name |
| network | Network/location name |
| ssid_name | SSID name |
| ssid_id | EnGenius internal SSID ID |
| enabled | Whether SSID is enabled |
| vlan_id | VLAN ID assigned to SSID |
| auth_type | Authentication type (WPA2-PSK, WPA3-Personal, disabled, etc.) |
| hidden | Whether SSID is hidden |
| client_isolation | Client isolation enabled |
| band_2_4g | 2.4GHz band enabled |
| band_5g | 5GHz band enabled |
| band_6g | 6GHz band enabled |

---

### engenius_switch_vlan_export.py

Exports all switches and VLAN configurations across all networks.

```bash
python3 engenius_switch_vlan_export.py
```

**Output:** `engenius_switches_TIMESTAMP.csv`

| Column | Description |
|--------|-------------|
| organization | Organization name |
| hierarchy_view | Hierarchy view name |
| network | Network/location name |
| switch_name | Switch device name |
| switch_id | EnGenius internal switch ID |
| model | Switch model number |
| mac | MAC address |
| serial_number | Serial number |

**Output:** `engenius_vlans_TIMESTAMP.csv`

| Column | Description |
|--------|-------------|
| organization | Organization name |
| hierarchy_view | Hierarchy view name |
| network | Network/location name |
| vlan_id | VLAN ID number |
| vlan_name | VLAN name |

---

### engenius_license_export.py

Exports all device license information, sorted by expiration date (expired/expiring first).

```bash
python3 engenius_license_export.py
```

**Output:** `engenius_licenses_TIMESTAMP.csv`

| Column | Description |
|--------|-------------|
| organization | Organization name |
| network_name | Network/location name |
| device_name | Device name |
| device_type | Device type (ap, switch, gateway, pdu, etc.) |
| model | Device model number |
| mac | MAC address |
| serial_number | Serial number |
| license_status | License status (active, expired, merging, etc.) |
| expiration_date | License expiration date (YYYY-MM-DD) |
| days_until_expiration | Days until expiration (negative = already expired) |

---

## API Reference

- **Documentation:** https://liveapi-console-dev.s3-us-west-2.amazonaws.com/engenius_cloud/falcon.html
- **Base URL:** `https://falcon.production.engenius.ai/v2`
- **Auth Header:** `api-key: YOUR_KEY`
- **Official Examples:** https://github.com/EnGenius-Cloud-Team/restful-api-example

### Endpoints Used

| Endpoint | Purpose |
|----------|---------|
| `GET /user/orgs` | List organizations |
| `GET /orgs/{orgId}/hvs` | List hierarchy views & networks |
| `GET /orgs/{orgId}/inventory` | Device inventory with license info |
| `GET /orgs/{orgId}/hvs/{hvId}/networks/{netId}/policy/aps/ssid-profiles` | SSID configs |
| `GET /orgs/{orgId}/hvs/{hvId}/networks/{netId}/devices/switches` | Switch devices |
| `GET /orgs/{orgId}/hvs/{hvId}/networks/{netId}/policy/vlans` | VLAN configs |

## Troubleshooting

| Error | Solution |
|-------|----------|
| "API Key Is Invalid" | Check `api_key.txt` has no extra whitespace, regenerate key if needed |
| "402 Payment Required" | API requires Pro license on your organization |
| Many 503 errors | EnGenius API temporarily unavailable, scripts retry 3x automatically |
