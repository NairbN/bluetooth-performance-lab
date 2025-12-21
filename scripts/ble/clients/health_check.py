#!/usr/bin/env python3
"""Health and dependency check for BLE lab environment."""

from __future__ import annotations

import json
import shutil
import subprocess
import sys
from pathlib import Path
from typing import Dict, List


def _run(cmd: List[str]) -> str:
    try:
        return subprocess.check_output(cmd, stderr=subprocess.STDOUT, text=True).strip()
    except Exception:
        return ""


def check_python_deps() -> Dict[str, str]:
    status = {}
    for mod in ["bleak", "matplotlib", "dbus_next"]:
        try:
            __import__(mod)
            status[mod] = "ok"
        except Exception:
            status[mod] = "missing"
    return status


def check_adapter() -> Dict[str, str]:
    info = {"powered": "unknown", "le_only": "unknown", "adapter": "unknown", "mac": "unknown"}
    btctl = shutil.which("bluetoothctl")
    if btctl:
        output = _run([btctl, "show"])
        for line in output.splitlines():
            if "Name:" in line:
                info["adapter"] = line.split("Name:")[-1].strip()
            if "Address:" in line:
                info["mac"] = line.split("Address:")[-1].strip()
            if "Powered:" in line:
                info["powered"] = line.split("Powered:")[-1].strip().lower()
    btmgmt = shutil.which("btmgmt")
    if btmgmt:
        output = _run([btmgmt, "info"])
        for line in output.splitlines():
            if "le" in line.lower() and "yes" in line.lower():
                info["le_only"] = "yes" if "bredr" in line.lower() and "no" in line.lower() else info["le_only"]
            if "bredr" in line.lower() and "no" in line.lower():
                info["le_only"] = "yes"
            elif "bredr" in line.lower() and "yes" in line.lower():
                info["le_only"] = "no"
    return info


def check_bluetoothd() -> str:
    systemctl = shutil.which("systemctl")
    if not systemctl:
        return "unknown"
    status = _run([systemctl, "cat", "bluetooth.service"])
    if "--experimental" in status:
        return "experimental_enabled"
    return "experimental_unknown"


def main() -> None:
    result = {
        "python_deps": check_python_deps(),
        "adapter": check_adapter(),
        "bluetoothd": check_bluetoothd(),
    }
    print(json.dumps(result, indent=2))


if __name__ == "__main__":
    main()
