from datetime import datetime, timezone, timedelta
from decimal import Decimal
from typing import Optional, List, Tuple

from dateutil import parser as dt_parser
from openpaygo import generate_token, TokenType

from models import Device, CreditUpdateIn


# -----------------------------------------------------------------------------
# Utility functions
# -----------------------------------------------------------------------------


def _parse_iso_datetime(value: str) -> datetime:
    dt = dt_parser.isoparse(value)
    if dt.tzinfo is None:
        dt = dt.replace(tzinfo=timezone.utc)
    return dt.astimezone(timezone.utc)


def _serialize_list(value: Optional[List[str]]) -> Optional[str]:
    if value is None:
        return None
    import json

    return json.dumps(value)


def _deserialize_list(value: Optional[str]) -> Optional[List[str]]:
    if value is None:
        return None
    import json

    return json.loads(value)


def compute_days_to_add(device: Device, credit_update: CreditUpdateIn) -> Tuple[int, datetime]:    
    current_effective = _parse_iso_datetime(device.effective_credit_value)
    now = datetime.now(timezone.utc)
    base = current_effective if current_effective > now else now
    requested = _parse_iso_datetime(credit_update.credit_value)
    if credit_update.credit_update_type == "ADD_CREDIT":
        delta = requested - base
    else:
        delta = requested - now
    days = Decimal(delta.total_seconds()) / Decimal(86400)
    rounded = int(days.to_integral_value(rounding="ROUND_HALF_UP"))
    days_rounded = max(0, rounded)
    if credit_update.credit_update_type == "ADD_CREDIT":
        effective_date = base + timedelta(days=days_rounded)
    else:
        effective_date = now + timedelta(days=days_rounded)
    return days_rounded, effective_date
        


def generate_openpaygo_token(device: Device, days_to_add: int, credit_update_type: str = "ADD_CREDIT") -> Tuple[str, int]:
    """
    Generate an OpenPAYGO token for the given number of days, updating token_count.

    This uses the ``generate_token`` helper from the OpenPAYGO-python library:
    https://github.com/EnAccess/OpenPAYGO-python
    """
    # secret_key must be set per device; enforce this explicitly
    if not device.secret_key:
        raise ValueError("Device secret_key is not configured")

    starting_code = (
        device.starting_code
        if device.starting_code is not None
        else None
    )
    value_divider = (
        device.value_divider
        if device.value_divider is not None
        else 1
    )
    restricted_digit_set = (
        device.restricted_digit_set
        if device.restricted_digit_set is not None
        else False
    )

    current_count = device.token_count

    # Determine token type based on credit_update_type
    if credit_update_type == "DISABLE_PAYG":
        token_type = TokenType.DISABLE_PAYG
        token_value = None
    elif credit_update_type == "SET_CREDIT":
        token_type = TokenType.SET_TIME
        token_value = days_to_add
    else:  # ADD_CREDIT
        token_type = TokenType.ADD_TIME
        token_value = days_to_add

    # Generate token for DISABLE_PAYG, SET_CREDIT, or when days_to_add > 0
    if credit_update_type == "DISABLE_PAYG" or credit_update_type == "SET_CREDIT" or (days_to_add > 0):
        # Delegate actual token computation to the library helper.
        print(f"Generating token for {credit_update_type} with value {token_value} and count {current_count}")
        new_count, token_str = generate_token(
            value=token_value,
            count=current_count,
            secret_key=device.secret_key,
            token_type=token_type,
            starting_code=starting_code,
            value_divider=value_divider,
            restricted_digit_set=restricted_digit_set,
        )

        return _format_token(token_str), new_count
    else:
        return "", current_count

def _format_token(token):
    token = ' '.join(token[i:i + 3] for i in range(0, len(token), 3))
    return token


# Export utility functions that may be used elsewhere
__all__ = [
    "compute_days_to_add",
    "generate_openpaygo_token",
    "_parse_iso_datetime",
    "_serialize_list",
    "_deserialize_list",
]

