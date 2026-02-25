#!/usr/bin/env python3
"""
Combine EnGenius export CSVs into a single Excel workbook.
Each CSV becomes a tab. Tab names derived from filenames.

Usage:
    python3 combine_csvs_to_xlsx.py <folder_path>
    python3 combine_csvs_to_xlsx.py engenius_export_xyz
Requires: openpyxl
"""

import sys
import os
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

import csv
import glob
from datetime import datetime

try:
    from openpyxl import Workbook
    from openpyxl.styles import Font, PatternFill, Alignment, Border, Side
    from openpyxl.utils import get_column_letter
except ImportError:
    print("ERROR: openpyxl not installed")
    print("  pip install openpyxl")
    sys.exit(1)


def csv_to_tab_name(filename):
    """Convert 'Florida - Wireless APs.csv' -> 'FL - APs' style tab name."""
    name = os.path.splitext(filename)[0]  # strip .csv

    # State abbreviation map
    abbrev = {
        "Alabama": "AL", "Alaska": "AK", "Arizona": "AZ", "Arkansas": "AR",
        "California": "CA", "Colorado": "CO", "Connecticut": "CT", "Delaware": "DE",
        "Florida": "FL", "Georgia": "GA", "Hawaii": "HI", "Idaho": "ID",
        "Illinois": "IL", "Indiana": "IN", "Iowa": "IA", "Kansas": "KS",
        "Kentucky": "KY", "Louisiana": "LA", "Maine": "ME", "Maryland": "MD",
        "Massachusetts": "MA", "Michigan": "MI", "Minnesota": "MN", "Mississippi": "MS",
        "Missouri": "MO", "Montana": "MT", "Nebraska": "NE", "Nevada": "NV",
        "New Hampshire": "NH", "New Jersey": "NJ", "New Mexico": "NM", "New York": "NY",
        "North Carolina": "NC", "North Dakota": "ND", "Ohio": "OH", "Oklahoma": "OK",
        "Oregon": "OR", "Pennsylvania": "PA", "Rhode Island": "RI", "South Carolina": "SC",
        "South Dakota": "SD", "Tennessee": "TN", "Texas": "TX", "Utah": "UT",
        "Vermont": "VT", "Virginia": "VA", "Washington": "WA", "West Virginia": "WV",
        "Wisconsin": "WI", "Wyoming": "WY"
    }

    for state, ab in abbrev.items():
        if name.startswith(state):
            name = name.replace(state, ab, 1)
            break

    # Shorten "Wireless APs" -> "APs"
    name = name.replace("Wireless APs", "APs")

    # Excel tab names max 31 chars
    return name[:31]


def main():
    if len(sys.argv) < 2:
        print("Usage: python3 combine_csvs_to_xlsx.py <csv_folder>")
        sys.exit(1)

    folder = sys.argv[1]
    if not os.path.isdir(folder):
        print(f"ERROR: '{folder}' is not a directory")
        sys.exit(1)

    csv_files = sorted(glob.glob(os.path.join(folder, "*.csv")))
    if not csv_files:
        print(f"No CSV files found in {folder}")
        sys.exit(1)

    print(f"Found {len(csv_files)} CSV(s) in {folder}")

    wb = Workbook()
    wb.remove(wb.active)  # remove default sheet

    # Styles
    header_font = Font(bold=True, color="FFFFFF", size=11)
    header_fill = PatternFill(start_color="2F5496", end_color="2F5496", fill_type="solid")
    header_align = Alignment(horizontal="center", vertical="center")
    thin_border = Border(
        left=Side(style="thin", color="D9D9D9"),
        right=Side(style="thin", color="D9D9D9"),
        top=Side(style="thin", color="D9D9D9"),
        bottom=Side(style="thin", color="D9D9D9")
    )
    expired_fill = PatternFill(start_color="FFC7CE", end_color="FFC7CE", fill_type="solid")
    expiring_fill = PatternFill(start_color="FFEB9C", end_color="FFEB9C", fill_type="solid")
    online_font = Font(color="006100")
    offline_font = Font(color="9C0006")

    for csv_path in csv_files:
        filename = os.path.basename(csv_path)
        tab_name = csv_to_tab_name(filename)
        print(f"  {filename} -> [{tab_name}]")

        ws = wb.create_sheet(title=tab_name)

        with open(csv_path, "r", newline="", encoding="utf-8-sig") as f:
            reader = csv.reader(f)
            for row_idx, row in enumerate(reader, 1):
                for col_idx, value in enumerate(row, 1):
                    cell = ws.cell(row=row_idx, column=col_idx, value=value)
                    cell.border = thin_border

                    if row_idx == 1:
                        # Header row
                        cell.font = header_font
                        cell.fill = header_fill
                        cell.alignment = header_align
                    else:
                        # Color-code license status
                        if cell.value == "EXPIRED":
                            cell.fill = expired_fill
                        elif cell.value == "EXPIRING SOON":
                            cell.fill = expiring_fill
                        elif cell.value == "Online":
                            cell.font = online_font
                        elif cell.value == "Offline":
                            cell.font = offline_font

        # Auto-width columns
        for col in range(1, ws.max_column + 1):
            max_len = 0
            col_letter = get_column_letter(col)
            for row in range(1, ws.max_row + 1):
                val = ws.cell(row=row, column=col).value
                if val:
                    max_len = max(max_len, len(str(val)))
            ws.column_dimensions[col_letter].width = min(max_len + 3, 40)

        # Freeze header row
        ws.freeze_panes = "A2"
        # Auto-filter
        ws.auto_filter.ref = f"A1:{get_column_letter(ws.max_column)}{ws.max_row}"

    # Output
    timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
    output_path = os.path.join(os.path.dirname(folder.rstrip("/\\")), f"EnGenius_Device_Report_{timestamp}.xlsx")
    wb.save(output_path)
    print(f"\nSaved: {output_path}")
    print(f"Tabs: {len(wb.sheetnames)}")


if __name__ == "__main__":
    main()
