import os
from typing import List, Optional

from pydantic import BaseModel, Field, ValidationError
from pony.orm import Database, PrimaryKey, Required, Optional as PonyOptional, Set
from datetime import datetime, timezone

# -----------------------------------------------------------------------------
# Database configuration
# -----------------------------------------------------------------------------

db = Database()


def init_db() -> None:
    """
    Bind Pony ORM to either SQLite or Postgres depending on env vars.
    """
    provider = os.getenv("DB_PROVIDER", "sqlite").lower()
    if provider == "postgres":
        db.bind(
            provider="postgres",
            host=os.getenv("DB_HOST", "localhost"),
            user=os.getenv("DB_USER", "postgres"),
            port=os.getenv("DB_PORT", 5432),
            password=os.getenv("DB_PASSWORD", ""),
            database=os.getenv("DB_NAME", "openpaygo"),
        )
    else:
        # Default: SQLite file
        db.bind(
            provider="sqlite",
            filename=os.getenv("SQLITE_FILE", "openpaygo.db"),
            create_db=True,
        )


# -----------------------------------------------------------------------------
# Entities
# -----------------------------------------------------------------------------


class Device(db.Entity):
    serial_number = PrimaryKey(str, max_len=50)
    model = PonyOptional(str, max_len=50)
    payg_mode = Required(int)  # TIME=1, USAGE=2, DISABLED=3
    credit_unit = PonyOptional(str)  # e.g. ABSOLUTE_TIME
    credit_value = Required(str)  # as provided
    effective_credit_value = Required(str)  # as applied
    pending_token_limit = PonyOptional(int)
    token_count = PonyOptional(int, default=0)
    # OpenPAYGO token configuration (secret_key is required)
    secret_key = Required(str, max_len=64)
    starting_code = PonyOptional(int)
    value_divider = PonyOptional(int)
    restricted_digit_set = PonyOptional(bool)

    credit_updates = Set("CreditUpdate")


class CreditUpdate(db.Entity):
    uuid = PrimaryKey(str)
    device = Required(Device)
    time = Required(str)
    commit_time = PonyOptional(str)
    status = Required(str, default="COMMITTED")
    status_details = PonyOptional(str)
    credit_unit = Required(str, default="ABSOLUTE_TIME")
    credit_value = Required(str)
    credit_update_type = Required(str, default="ADD_CREDIT")
    credit_update_mode = Required(str, default="AUTO")
    effective_credit_value = Required(str)
    effective_credit_update_type = Required(str)
    effective_credit_update_mode = Required(str)
    token = PonyOptional(str)
    token_count = PonyOptional(int)


# -----------------------------------------------------------------------------
# Constants
# -----------------------------------------------------------------------------

# These are constants for all devices (not stored per-device)
SUPPORTED_CREDIT_UNITS = ["ABSOLUTE_TIME", "DAYS"]
SUPPORTED_CREDIT_UPDATE_TYPES = ["ADD_CREDIT", "SET_CREDIT", "DISABLE_PAYG"]
SUPPORTED_CREDIT_UPDATE_MODES = ["TOKEN", "AUTO"]


# -----------------------------------------------------------------------------
# Pydantic models
# -----------------------------------------------------------------------------


class DeviceIn(BaseModel):
    serial_number: str = Field(..., max_length=50)
    model: Optional[str] = Field(None, max_length=50)
    payg_mode: int  # TIME=1, USAGE=2, DISABLED=3
    credit_unit: Optional[str] = None
    credit_value: str
    effective_credit_value: str
    pending_token_limit: Optional[int] = 0
    token_count: Optional[int] = 0
    # OpenPAYGO token configuration; secret_key is required per device
    secret_key: str = Field(
        ...,
        description="32-hex-char OpenPAYGO secret key for this device",
        max_length=64,
    )
    starting_code: Optional[int] = Field(
        default=None,
        description="Starting code / seed for token generation",
    )
    value_divider: Optional[int] = Field(
        default=None,
        description="Value divider for token generation (defaults to 1)",
    )
    restricted_digit_set: Optional[bool] = Field(
        default=None,
        description="Whether to use restricted digit set",
    )


class DeviceOut(DeviceIn):
    # These are constants returned for all devices (not stored in DB)
    supported_credit_units: List[str] = Field(
        default_factory=lambda: SUPPORTED_CREDIT_UNITS,
        description="Supported credit units (constant for all devices)",
    )
    supported_credit_update_types: List[str] = Field(
        default_factory=lambda: SUPPORTED_CREDIT_UPDATE_TYPES,
        description="Supported credit update types (constant for all devices)",
    )
    supported_credit_update_modes: List[str] = Field(
        default_factory=lambda: SUPPORTED_CREDIT_UPDATE_MODES,
        description="Supported credit update modes (constant for all devices)",
    )


class CreditUpdateIn(BaseModel):
    device_serial_number: str
    time: Optional[str] = datetime.now(timezone.utc).isoformat().replace("+00:00", "Z")
    commit_time: Optional[str] = datetime.now(timezone.utc).isoformat().replace("+00:00", "Z")
    status: str = "COMMITTED"
    status_details: Optional[List[str]] = None
    credit_unit: str = "ABSOLUTE_TIME"
    credit_value: str
    credit_update_type: str = "ADD_CREDIT"
    credit_update_mode: str = "AUTO"


class CreditUpdateOut(BaseModel):
    uuid: str
    device_serial_number: str
    time: str
    commit_time: Optional[str]
    status: str
    status_details: Optional[List[str]] = None
    credit_unit: str
    credit_value: str
    credit_update_type: str
    credit_update_mode: str
    effective_credit_value: str
    effective_credit_update_type: str
    effective_credit_update_mode: str
    token: Optional[str] = None
    token_count: Optional[int] = None

