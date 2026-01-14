import os
import json
from datetime import datetime, timedelta, timezone
import uuid

import pytest
from freezegun import freeze_time
from pony.orm import db_session

# Ensure the project root (where app.py lives) is on sys.path when running in Docker/pytest
PROJECT_ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), os.pardir))
if PROJECT_ROOT not in os.sys.path:
    os.sys.path.insert(0, PROJECT_ROOT)

from app import app
from models import (
    Device,
    CreditUpdate,
    db,
    SUPPORTED_CREDIT_UNITS,
    SUPPORTED_CREDIT_UPDATE_TYPES,
    SUPPORTED_CREDIT_UPDATE_MODES,
)


@pytest.fixture
def client():
    app.testing = True
    with app.test_client() as c:
        yield c


def post_device_credit_update_v2(client, payload):
    """Helper function to post a credit update request (v2-style API)."""
    uuid_str = str(uuid.uuid4())
    now = datetime.now(timezone.utc)
    # Build the full payload with defaults
    full_payload = {
        "device_serial_number": payload.get("device_serial_number", TEST_DEVICE_SERIAL),
        "time": now.isoformat().replace("+00:00", "Z"),
        "commit_time": now.isoformat().replace("+00:00", "Z"),
        "status": "COMMITTED",
        "status_details": [],
        "credit_unit": payload.get("credit_unit", "DAYS"),
        "credit_value": payload.get("credit_value", "0"),
        "credit_update_type": payload.get("credit_update_type", "ADD_CREDIT"),
        "credit_update_mode": "AUTO",
    }
    response = client.post(f"/credit_updates/{uuid_str}", json=full_payload)
    json_data = response.get_json() if response.data else None
    return response, json_data


def test_health(client):
    resp = client.get("/health")
    assert resp.status_code == 200
    data = resp.get_json()
    assert data == {"status": "ok"}


def test_create_and_list_devices(client):
    device_payload = {
        "serial_number": "S1234",
        "model": "SK499",
        "payg_mode": 1,
        "credit_unit": "ABSOLUTE_TIME",
        "credit_value": "2100-01-01T00:00:00Z",
        "effective_credit_value": "2100-01-01T00:00:00Z",
        "pending_token_limit": 0,
        "token_count": 0,
        "secret_key": "dac86b1a29ab82edc5fbbc41ec9530f6",
    }

    resp = client.post("/devices", json=device_payload)
    assert resp.status_code == 200
    created = resp.get_json()
    assert created["serial_number"] == "S1234"
    # Verify constants are returned
    assert created["supported_credit_units"] == SUPPORTED_CREDIT_UNITS
    assert created["supported_credit_update_types"] == SUPPORTED_CREDIT_UPDATE_TYPES
    assert created["supported_credit_update_modes"] == SUPPORTED_CREDIT_UPDATE_MODES

    resp = client.get("/devices")
    assert resp.status_code == 200
    devices = resp.get_json()
    assert isinstance(devices, list)
    assert len(devices) == 1
    assert devices[0] == "S1234"


def test_credit_update_generates_token_and_updates_effective_value(client):
    # Create a device with a far-future effective_credit_value so "now" does not affect computations
    device_payload = {
        "serial_number": "S9999",
        "model": "SK999",
        "payg_mode": 1,
        "credit_unit": "ABSOLUTE_TIME",
        "credit_value": "2100-01-01T00:00:00Z",
        "effective_credit_value": "2100-01-01T00:00:00Z",
        "pending_token_limit": 0,
        "token_count": 0,
        "secret_key": "dac86b1a29ab82edc5fbbc41ec9530f6",
    }
    resp = client.post("/devices", json=device_payload)
    assert resp.status_code == 200

    cu_payload = {
        "device_serial_number": "S9999",
        "time": "2099-12-31T00:00:00Z",
        "commit_time": "2099-12-31T00:00:00Z",
        "status": "COMMITTED",
        "status_details": [],
        "credit_unit": "ABSOLUTE_TIME",
        # 10 days after the device effective_credit_value so rounding is exact
        "credit_value": "2100-01-11T00:00:00Z",
        "credit_update_type": "ADD_CREDIT",
        "credit_update_mode": "AUTO",
    }

    resp = client.post("/credit_updates/111-222-333-ddd", json=cu_payload)
    assert resp.status_code == 200
    data = resp.get_json()

    # Token should be present and token_count should be an integer
    assert "token" in data
    assert data["token"] is not None and data["token"] != ""
    assert isinstance(data["token_count"], int)

    # Effective credit value should match the requested target value
    assert data["effective_credit_value"] == "2100-01-11T00:00:00Z"

    # Verify DB state matches
    with db_session:
        dev = Device.get(serial_number="S9999")
        assert dev is not None
        assert dev.effective_credit_value == "2100-01-11T00:00:00Z"
        assert dev.token_count == data["token_count"]


def test_credit_update_invalid_unit_returns_400(client):
    device_payload = {
        "serial_number": "S0001",
        "model": "SK0001",
        "payg_mode": 1,
        "credit_unit": "ABSOLUTE_TIME",
        "credit_value": "2100-01-01T00:00:00Z",
        "effective_credit_value": "2100-01-01T00:00:00Z",
        "pending_token_limit": 0,
        "token_count": 0,
        "secret_key": "dac86b1a29ab82edc5fbbc41ec9530f6",
    }
    client.post("/devices", json=device_payload)

    cu_payload = {
        "device_serial_number": "S0001",
        "time": "2099-12-31T00:00:00Z",
        "commit_time": "2099-12-31T00:00:00Z",
        "status": "COMMITTED",
        "status_details": [],
        "credit_unit": "INVALID_UNIT",  # unsupported
        "credit_value": "2100-01-11T00:00:00Z",
        "credit_update_type": "ADD_CREDIT",
        "credit_update_mode": "AUTO",
    }

    resp = client.post("/credit_updates/bad-unit", json=cu_payload)
    assert resp.status_code == 400
    data = resp.get_json()
    assert "Unsupported credit_unit" in data["error"]


def test_credit_update_device_not_found_returns_404(client):
    cu_payload = {
        "device_serial_number": "UNKNOWN",
        "time": "2099-12-31T00:00:00Z",
        "commit_time": "2099-12-31T00:00:00Z",
        "status": "COMMITTED",
        "status_details": [],
        "credit_unit": "ABSOLUTE_TIME",
        "credit_value": "2100-01-11T00:00:00Z",
        "credit_update_type": "ADD_CREDIT",
        "credit_update_mode": "AUTO",
    }

    resp = client.post("/credit_updates/not-found", json=cu_payload)
    assert resp.status_code == 404
    data = resp.get_json()
    assert data["error"] == "Device not found"

# Test device configuration from old implementation
TEST_DEVICE_SERIAL = "TEST_DEVICE_001"
def test_create_test_device(client):
    """Create a test device with the specified configuration from old implementation."""
    now = datetime.now(timezone.utc)
    device_payload = {
        "serial_number": TEST_DEVICE_SERIAL,
        "model": "TEST_MODEL",
        "payg_mode": 1,
        "credit_unit": "ABSOLUTE_TIME",
        "credit_value": now.isoformat().replace("+00:00", "Z"),
        "effective_credit_value": now.isoformat().replace("+00:00", "Z"),
        "pending_token_limit": 0,
        "token_count": 1,
        "secret_key": "a29ab82edc5fbbc41ec9530f6dac86b1",
        "starting_code": 123456789,
    }
    resp = client.post("/devices", json=device_payload)
    assert resp.status_code == 200


# Tests based on old implementation with expected token values
def test_days_1_day(client):
    response, json_data = post_device_credit_update_v2(client, {
        "device_serial_number": TEST_DEVICE_SERIAL,
        "credit_unit": "DAYS",
        "credit_value": "1",
        "credit_update_type": "ADD_CREDIT"
    })
    assert response.status_code == 200
    assert json_data['token'] == '662 486 790'  # Code valid for 1 days


def test_days_29_day(client):
    response, json_data = post_device_credit_update_v2(client, {
        "device_serial_number": TEST_DEVICE_SERIAL,
        "credit_unit": "DAYS",
        "credit_value": "29",
        "credit_update_type": "ADD_CREDIT"
    })
    assert response.status_code == 200
    assert json_data['token'] == '927 706 818'  # Code valid for 29 extra days


def test_disable_payg_days(client):
    response, json_data = post_device_credit_update_v2(client, {
        "device_serial_number": TEST_DEVICE_SERIAL,
        "credit_update_type": "DISABLE_PAYG"
    })
    assert response.status_code == 200
    assert json_data['token'] == '129 635 787'  # Code valid for Disable PAYG


def test_days_set_0_deactivate(client):
    response, json_data = post_device_credit_update_v2(client, {
        "device_serial_number": TEST_DEVICE_SERIAL,
        "credit_unit": "DAYS",
        "credit_value": "0",
        "credit_update_type": "SET_CREDIT"
    })
    assert response.status_code == 200
    assert json_data['token'] == '295 647 789'  # Deactivates (set time for 0 days)


@freeze_time(datetime.now() + timedelta(days=35))
def test_add_30_days_2(client):
    response, json_data = post_device_credit_update_v2(client, {
        "device_serial_number": TEST_DEVICE_SERIAL,
        "credit_unit": "DAYS",
        "credit_value": "30",
        "credit_update_type": "ADD_CREDIT"
    })
    assert response.status_code == 200
    assert json_data['token'] == '451 306 819'  # ADD 30 days


@freeze_time(datetime.now() + timedelta(days=35))
def test_add_time_3_days(client):
    response, json_data = post_device_credit_update_v2(client, {
        "device_serial_number": TEST_DEVICE_SERIAL,
        "credit_unit": "DAYS",
        "credit_value": "3",
        "credit_update_type": "ADD_CREDIT"
    })
    assert response.status_code == 200
    assert json_data['token'] == '440 471 792'  # ADD 3 days


@freeze_time(datetime.now() + timedelta(days=35))
def test_set_time_15_days(client):
    response, json_data = post_device_credit_update_v2(client, {
        "device_serial_number": TEST_DEVICE_SERIAL,
        "credit_unit": "DAYS",
        "credit_value": "15",
        "credit_update_type": "SET_CREDIT"
    })
    assert response.status_code == 200
    assert json_data['token'] == '970 188 804'  # SET 15 days


@freeze_time(datetime.now() + timedelta(days=35))
def test_set_time_18_days(client):
    response, json_data = post_device_credit_update_v2(client, {
        "device_serial_number": TEST_DEVICE_SERIAL,
        "credit_unit": "DAYS",
        "credit_value": "18",
        "credit_update_type": "SET_CREDIT"
    })
    assert response.status_code == 200
    assert json_data['token'] == '754 093 807'  # Set to 18 days


@freeze_time(datetime.now() + timedelta(days=35))
def test_set_time_33_2_days(client):
    response, json_data = post_device_credit_update_v2(client, {
        "device_serial_number": TEST_DEVICE_SERIAL,
        "credit_unit": "DAYS",
        "credit_value": "33",
        "credit_update_type": "SET_CREDIT"
    })
    assert response.status_code == 200
    assert json_data['token'] == '296 943 822'  # Set to 33 days


@freeze_time(datetime.now() + timedelta(days=35))
def test_add_time_2_days(client):
    response, json_data = post_device_credit_update_v2(client, {
        "device_serial_number": TEST_DEVICE_SERIAL,
        "credit_unit": "DAYS",
        "credit_value": "2",
        "credit_update_type": "ADD_CREDIT"
    })
    assert response.status_code == 200
    assert json_data['token'] == '935 928 791'  # ADD 2 days

