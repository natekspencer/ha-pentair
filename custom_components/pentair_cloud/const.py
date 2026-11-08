"""Pentair constants."""

from __future__ import annotations

from typing import Final

DOMAIN: Final = "pentair_cloud"

CONF_ID_TOKEN: Final = "id_token"
CONF_REFRESH_TOKEN: Final = "refresh_token"

# Device fields that are secrets, so are never exposed as entities
SECRET_FIELDS: Final = {
    # IntelliFlo pump fields
    "s11",  # Security key
    "d15",  # Password
}

# Kept out of diagnostics and debug logs
TO_REDACT: Final = {
    # Account and device identifiers
    "arn",
    "deviceId",
    "email",
    "userId",
    # IntelliFlo pump network details
    "s6",  # Wifi mac address
    "s23",  # SSID
    *SECRET_FIELDS,
}
