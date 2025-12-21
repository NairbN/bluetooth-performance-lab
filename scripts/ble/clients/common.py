"""Shared helpers for BLE clients (connection, services, utilities)."""

from __future__ import annotations

import asyncio
from datetime import datetime, timezone
from typing import Any, Dict, Optional, Tuple

from bleak import BleakClient


def utc_now() -> str:
    return datetime.now(timezone.utc).isoformat()


async def safe_disconnect(client: BleakClient) -> None:
    try:
        await client.disconnect()
    except Exception:
        pass


async def connect_with_retries(
    address: str,
    *,
    timeout_s: float,
    attempts: int,
    retry_delay_s: float,
    adapter: Optional[str] = None,
    address_type: Optional[str] = None,
    logger_prefix: str = "[ble]",
) -> Tuple[BleakClient, int]:
    attempts = max(1, attempts)
    for attempt in range(1, attempts + 1):
        client = BleakClient(address, timeout=timeout_s, adapter=adapter, address_type=address_type)
        try:
            await client.connect(timeout=timeout_s)
            print(f"{logger_prefix} Connected to {address} on attempt {attempt}/{attempts}", flush=True)
            return client, attempt
        except asyncio.CancelledError:
            await safe_disconnect(client)
            raise
        except Exception as exc:  # pylint: disable=broad-except
            await safe_disconnect(client)
            print(f"{logger_prefix} Connection attempt {attempt}/{attempts} failed: {exc}", flush=True)
            if attempt < attempts:
                await asyncio.sleep(retry_delay_s)
            else:
                raise RuntimeError(
                    f"Failed to connect to {address} after {attempts} attempts ({exc})."
                ) from exc
    raise RuntimeError(f"Failed to connect to {address}; retries exhausted.")


async def resolve_services(client: BleakClient):
    try:
        return client.services
    except Exception:
        get_services = getattr(client, "get_services", None)
        if callable(get_services):
            return await get_services()
        raise RuntimeError("Bleak client services not available yet.")


def validate_characteristics(services, service_uuid: str, tx_uuid: str, rx_uuid: str):
    service = services.get_service(service_uuid)
    if service is None:
        raise RuntimeError(f"Service {service_uuid} not found on device")
    tx_char = service.get_characteristic(tx_uuid)
    rx_char = service.get_characteristic(rx_uuid)
    if tx_char is None or rx_char is None:
        raise RuntimeError("TX/RX characteristics not found in service")
    return tx_char, rx_char


async def attempt_mtu_request(client: BleakClient, mtu: int) -> Dict[str, Any]:
    info: Dict[str, Any] = {"requested": mtu}
    request_fn = getattr(client, "request_mtu", None)
    if callable(request_fn):
        try:
            negotiated = await request_fn(mtu)
            info["status"] = "success"
            info["negotiated"] = negotiated
        except Exception as exc:  # pylint: disable=broad-except
            info["status"] = "failed"
            info["error"] = str(exc)
    else:
        info["status"] = "unsupported_by_bleak"
    return info


async def attempt_phy_request(client: BleakClient, phy: str) -> Dict[str, Any]:
    info: Dict[str, Any] = {"requested": phy}
    if phy == "auto":
        info["status"] = "skipped"
        return info
    request_fn = getattr(client, "set_preferred_phy", None)
    if callable(request_fn):
        try:
            await request_fn(tx_phys=phy, rx_phys=phy)
            info["status"] = "success"
        except Exception as exc:  # pylint: disable=broad-except
            info["status"] = "failed"
            info["error"] = str(exc)
    else:
        info["status"] = "unsupported_by_bleak"
    return info
