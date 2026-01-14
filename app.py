import csv
import io
import os
from datetime import datetime, timezone, timedelta
from functools import wraps
from typing import List, Optional

from flask import Flask, jsonify, request, Response, render_template
from pydantic import ValidationError
from pony.orm import db_session

from models import (
    db,
    init_db,
    Device,
    CreditUpdate,
    DeviceIn,
    DeviceOut,
    CreditUpdateIn,
    CreditUpdateOut,
    SUPPORTED_CREDIT_UNITS,
    SUPPORTED_CREDIT_UPDATE_TYPES,
    SUPPORTED_CREDIT_UPDATE_MODES,
)
from token_logic import (
    compute_days_to_add,
    generate_openpaygo_token,
    _parse_iso_datetime,
    _serialize_list,
    _deserialize_list,
)


# -----------------------------------------------------------------------------
# Flask application
# -----------------------------------------------------------------------------

app = Flask(__name__)

# Initialize database on import
init_db()
db.generate_mapping(create_tables=True)


# -----------------------------------------------------------------------------
# Bearer Token Authentication for API Routes
# -----------------------------------------------------------------------------


def check_bearer_token(token: str) -> bool:
    """Check if bearer token is valid."""
    expected_token = os.getenv("API_BEARER_TOKEN")
    if not expected_token:
        # If no token is set, authentication is disabled (for development)
        return True
    return token == expected_token


def requires_bearer_token(f):
    """Decorator for API routes that require bearer token authentication."""

    @wraps(f)
    def decorated(*args, **kwargs):
        if not os.getenv("API_BEARER_TOKEN"):
            return f(*args, **kwargs)
        auth_header = request.headers.get("Authorization", "")
        if not auth_header.startswith("Bearer "):
            return jsonify({"error": "Authentication required", "message": "Bearer token missing or invalid"}), 401
        
        token = auth_header[7:]  # Remove "Bearer " prefix
        if not check_bearer_token(token):
            return jsonify({"error": "Authentication failed", "message": "Invalid bearer token"}), 401
        
        return f(*args, **kwargs)

    return decorated


# -----------------------------------------------------------------------------
# Routes
# -----------------------------------------------------------------------------


@app.route("/devices", methods=["POST"])
@requires_bearer_token
@db_session
def add_device():
    payload = request.get_json(force=True, silent=True) or {}
    try:
        device_in = DeviceIn(**payload)
    except ValidationError as e:
        return jsonify({"error": "Validation error", "details": e.errors()}), 400

    existing = Device.get(serial_number=device_in.serial_number)
    if existing:
        return jsonify({"error": "Device already exists"}), 400

    dev = Device(
        serial_number=device_in.serial_number,
        model=device_in.model,
        payg_mode=device_in.payg_mode,
        credit_unit=device_in.credit_unit,
        credit_value=device_in.credit_value,
        effective_credit_value=device_in.effective_credit_value,
        pending_token_limit=device_in.pending_token_limit,
        token_count=device_in.token_count,
        secret_key=device_in.secret_key,
        starting_code=device_in.starting_code,
        value_divider=device_in.value_divider,
        restricted_digit_set=device_in.restricted_digit_set,
    )

    out = DeviceOut(
        serial_number=dev.serial_number,
        model=dev.model,
        payg_mode=dev.payg_mode,
        credit_unit=dev.credit_unit,
        credit_value=dev.credit_value,
        effective_credit_value=dev.effective_credit_value,
        pending_token_limit=dev.pending_token_limit,
        token_count=dev.token_count,
        secret_key=dev.secret_key,
        starting_code=dev.starting_code,
        value_divider=dev.value_divider,
        restricted_digit_set=dev.restricted_digit_set,
    )
    return jsonify(out.model_dump())


@app.route("/devices", methods=["GET"])
@requires_bearer_token
@db_session
def list_devices():
    include_objects = request.args.get("include_objects", "false").lower() == "true"
    
    devices = Device.select()[:]
    
    if include_objects:
        result: List[DeviceOut] = []
        for dev in devices:
            result.append(
                DeviceOut(
                    serial_number=dev.serial_number,
                    model=dev.model,
                    payg_mode=dev.payg_mode,
                    credit_unit=dev.credit_unit,
                    credit_value=dev.credit_value,
                    effective_credit_value=dev.effective_credit_value,
                    pending_token_limit=dev.pending_token_limit,
                    token_count=dev.token_count,
                    secret_key=dev.secret_key,
                    starting_code=dev.starting_code,
                    value_divider=dev.value_divider,
                    restricted_digit_set=dev.restricted_digit_set,
                )
            )
        return jsonify([d.model_dump() for d in result])
    else:
        # Return just serial numbers
        return jsonify([dev.serial_number for dev in devices])


@app.route("/devices/<serial_number>", methods=["GET"])
@requires_bearer_token
@db_session
def get_device(serial_number: str):
    """
    Get a specific device by serial number.
    """
    dev = Device.get(serial_number=serial_number)
    if not dev:
        return jsonify({"error": "Device not found"}), 404

    out = DeviceOut(
        serial_number=dev.serial_number,
        model=dev.model,
        payg_mode=dev.payg_mode,
        credit_unit=dev.credit_unit,
        credit_value=dev.credit_value,
        effective_credit_value=dev.effective_credit_value,
        pending_token_limit=dev.pending_token_limit,
        token_count=dev.token_count,
        secret_key=dev.secret_key,
        starting_code=dev.starting_code,
        value_divider=dev.value_divider,
        restricted_digit_set=dev.restricted_digit_set,
    )
    return jsonify(out.model_dump())


@app.route("/devices/<serial_number>", methods=["PUT"])
@requires_bearer_token
@db_session
def update_device(serial_number: str):
    """
    Update an existing device configuration, including OpenPAYGO token settings.
    """
    payload = request.get_json(force=True, silent=True) or {}
    try:
        device_in = DeviceIn(**payload)
    except ValidationError as e:
        return jsonify({"error": "Validation error", "details": e.errors()}), 400

    dev = Device.get(serial_number=serial_number)
    if not dev:
        return jsonify({"error": "Device not found"}), 404

    dev.model = device_in.model
    dev.payg_mode = device_in.payg_mode
    dev.credit_unit = device_in.credit_unit
    dev.credit_value = device_in.credit_value
    dev.effective_credit_value = device_in.effective_credit_value
    dev.pending_token_limit = device_in.pending_token_limit
    dev.token_count = device_in.token_count
    dev.secret_key = device_in.secret_key
    dev.starting_code = device_in.starting_code
    dev.value_divider = device_in.value_divider
    dev.restricted_digit_set = device_in.restricted_digit_set

    out = DeviceOut(
        serial_number=dev.serial_number,
        model=dev.model,
        payg_mode=dev.payg_mode,
        credit_unit=dev.credit_unit,
        credit_value=dev.credit_value,
        effective_credit_value=dev.effective_credit_value,
        pending_token_limit=dev.pending_token_limit,
        token_count=dev.token_count,
        secret_key=dev.secret_key,
        starting_code=dev.starting_code,
        value_divider=dev.value_divider,
        restricted_digit_set=dev.restricted_digit_set,
    )
    return jsonify(out.model_dump())


@app.route("/credit_updates/<uuid>", methods=["POST"])
@requires_bearer_token
@db_session
def create_credit_update(uuid: str):
    payload = request.get_json(force=True, silent=True) or {}
    try:
        cu_in = CreditUpdateIn(**payload)
    except ValidationError as e:
        return jsonify({"error": "Validation error", "details": e.errors()}), 400

    device = Device.get(serial_number=cu_in.device_serial_number)
    if not device:
        return jsonify({"error": "Device not found"}), 404
    
    if cu_in.credit_unit not in SUPPORTED_CREDIT_UNITS:
        return jsonify({"error": f"Unsupported credit_unit: {cu_in.credit_unit}"}), 400
    if cu_in.credit_update_type not in SUPPORTED_CREDIT_UPDATE_TYPES:
        return jsonify({"error": f"Unsupported credit_update_type: {cu_in.credit_update_type}"}), 400
    if cu_in.credit_update_mode not in SUPPORTED_CREDIT_UPDATE_MODES:
        return jsonify({"error": f"Unsupported credit_update_mode: {cu_in.credit_update_mode}"}), 400

    # Handle DAYS credit_unit: convert to ABSOLUTE_TIME before processing
    original_credit_unit = cu_in.credit_unit
    original_credit_value = cu_in.credit_value
    if cu_in.credit_unit == "DAYS":
        try:
            days = int(cu_in.credit_value)
            now = datetime.now(timezone.utc)
            last_device_date = _parse_iso_datetime(device.effective_credit_value)
            
            # If last device date is in the past, use now + days, otherwise use last device date + days
            if last_device_date < now:
                target_date = now + timedelta(days=days)
            else:
                if cu_in.credit_update_type == "ADD_CREDIT":
                    target_date = last_device_date + timedelta(days=days)
                else:
                    target_date = now + timedelta(days=days)
            
            # Convert to ABSOLUTE_TIME format for processing
            cu_in.credit_value = target_date.isoformat().replace("+00:00", "Z")
            cu_in.credit_unit = "ABSOLUTE_TIME"
        except (ValueError, TypeError) as e:
            return jsonify({"error": f"Invalid credit_value for DAYS unit: {original_credit_value}"}), 400


    if cu_in.credit_update_type == "ADD_CREDIT" and cu_in.credit_value < device.effective_credit_value:
        effective_type = "SET_CREDIT"
    else:
        effective_type = cu_in.credit_update_type
    cu_in.credit_update_type = effective_type

    try:
        days_to_add, new_effective_date = compute_days_to_add(device, cu_in)
    except ValueError as e:
        return jsonify({"error": str(e)}), 400

    token, new_count = generate_openpaygo_token(device, days_to_add, cu_in.credit_update_type)

    # Update device state
    device.effective_credit_value = new_effective_date.isoformat().replace("+00:00", "Z")
    device.credit_value = original_credit_value
    device.token_count = new_count
    
    # Flush changes to ensure token_count is saved immediately
    db.commit()
    print(f"Token count after commit: {device.token_count}")

    effective_credit_value = device.effective_credit_value
    
    effective_type = cu_in.credit_update_type
    effective_mode = "TOKEN"

    status_details = cu_in.status_details or []
    if days_to_add <= 0 and cu_in.credit_update_type != "DISABLE_PAYG":
        status_details.append("NO_TOKEN_NEEDED")

    cu = CreditUpdate(
        uuid=uuid,
        device=device,
        time=cu_in.time,
        commit_time=cu_in.commit_time or cu_in.time,
        status=cu_in.status,
        status_details=_serialize_list(status_details),
        credit_unit=original_credit_unit,
        credit_value=original_credit_value,
        credit_update_type=cu_in.credit_update_type,
        credit_update_mode=cu_in.credit_update_mode,
        effective_credit_value=effective_credit_value,
        effective_credit_update_type=effective_type,
        effective_credit_update_mode=effective_mode,
        token=token or None,
        token_count=new_count if token else None,
    )

    out = CreditUpdateOut(
        uuid=cu.uuid,
        device_serial_number=device.serial_number,
        time=cu.time,
        commit_time=cu.commit_time,
        status=cu.status,
        status_details=_deserialize_list(cu.status_details),
        credit_unit=cu.credit_unit,
        credit_value=cu.credit_value,
        credit_update_type=cu.credit_update_type,
        credit_update_mode=cu.credit_update_mode,
        effective_credit_value=cu.effective_credit_value,
        effective_credit_update_type=cu.effective_credit_update_type,
        effective_credit_update_mode=cu.effective_credit_update_mode,
        token=cu.token,
        token_count=cu.token_count,
    )
    return jsonify(out.model_dump())


@app.route("/health", methods=["GET"])
def health():
    return jsonify({"status": "ok"})


@app.route("/support", methods=["GET"])
def support():
    return jsonify({"supported_credit_units": SUPPORTED_CREDIT_UNITS})


# -----------------------------------------------------------------------------
# CSV Upload with Basic Auth
# -----------------------------------------------------------------------------


def check_auth(username: str, password: str) -> bool:
    """Check if username/password combination is valid."""
    expected_username = os.getenv("CSV_UPLOAD_USERNAME", "admin")
    expected_password = os.getenv("CSV_UPLOAD_PASSWORD", "admin")
    return username == expected_username and password == expected_password


def requires_auth(f):
    """Decorator for routes that require basic authentication."""

    @wraps(f)
    def decorated(*args, **kwargs):
        auth = request.authorization
        if not auth or not check_auth(auth.username, auth.password):
            return Response(
                "Authentication required",
                401,
                {"WWW-Authenticate": 'Basic realm="Login Required"'},
            )
        return f(*args, **kwargs)

    return decorated


def _parse_bool(value: str) -> Optional[bool]:
    """Parse a string to boolean, handling common formats."""
    if not value or value.strip() == "":
        return None
    value_lower = value.strip().lower()
    if value_lower in ("true", "1", "yes", "y"):
        return True
    elif value_lower in ("false", "0", "no", "n"):
        return False
    return None


def _parse_int(value: str) -> Optional[int]:
    """Parse a string to integer, returning None if empty or invalid."""
    if not value or value.strip() == "":
        return None
    try:
        return int(value.strip())
    except ValueError:
        return None


@app.route("/upload-devices", methods=["GET"])
@requires_auth
def upload_devices_form():
    """Serve HTML form for CSV device upload."""
    return render_template("upload_form.html")


@app.route("/upload-devices", methods=["POST"])
@requires_auth
@db_session
def upload_devices():
    """Process CSV file and create devices."""
    if "csv_file" not in request.files:
        return render_template("upload_error.html", error_message="No file uploaded. Please select a CSV file."), 400

    file = request.files["csv_file"]
    if file.filename == "":
        return render_template("upload_error.html", error_message="No file selected."), 400

    # Read CSV content
    stream = io.StringIO(file.stream.read().decode("utf-8"))
    reader = csv.DictReader(stream)

    # Normalize column names (case-insensitive, strip whitespace)
    fieldnames = [col.strip().lower() for col in reader.fieldnames or []]
    reader.fieldnames = fieldnames

    # Map CSV columns to our field names
    column_map = {
        "serial number": "serial_number",
        "starting code": "starting_code",
        "key": "secret_key",
        "count": "token_count",
        "time divider": "value_divider",
        "restricted digit mode": "restricted_digit_set",
        "hardware model": "model",
        "version": "version",  # ignored
        "test code": "test_code",  # ignored
    }

    results = {
        "success": [],
        "errors": [],
        "skipped": [],
    }

    # Default values for required fields not in CSV
    default_payg_mode = 1  # TIME=1, USAGE=2, DISABLED=3
    default_credit_value = datetime.now(timezone.utc).isoformat().replace("+00:00", "Z")
    default_effective_credit_value = default_credit_value

    for row_num, row in enumerate(reader, start=2):  # start=2 because row 1 is header
        try:
            # Extract values using normalized column names
            serial_number = None
            secret_key = None
            model = None
            starting_code = None
            token_count = None
            value_divider = None
            restricted_digit_set = None

            for csv_col, our_field in column_map.items():
                if csv_col in row and row[csv_col]:
                    value = row[csv_col].strip()
                    if our_field == "serial_number":
                        serial_number = value
                    elif our_field == "secret_key":
                        secret_key = value
                    elif our_field == "model":
                        model = value
                    elif our_field == "starting_code":
                        starting_code = _parse_int(value)
                    elif our_field == "token_count":
                        token_count = _parse_int(value)
                    elif our_field == "value_divider":
                        value_divider = _parse_int(value)
                    elif our_field == "restricted_digit_set":
                        restricted_digit_set = _parse_bool(value)
                    # version and test_code are ignored

            # Validate required fields
            if not serial_number:
                results["errors"].append(f"Row {row_num}: Missing 'Serial Number'")
                continue

            if not secret_key:
                results["errors"].append(f"Row {row_num}: Missing 'Key' (secret_key is required)")
                continue

            # Check if device already exists
            existing = Device.get(serial_number=serial_number)
            if existing:
                results["skipped"].append(f"Row {row_num}: Device '{serial_number}' already exists")
                continue

            # Create device with defaults for required fields
            dev = Device(
                serial_number=serial_number,
                model=model,
                payg_mode=default_payg_mode,
                credit_unit="ABSOLUTE_TIME",
                credit_value=default_credit_value,
                effective_credit_value=default_effective_credit_value,
                pending_token_limit=0,
                token_count=token_count or 0,
                secret_key=secret_key,
                starting_code=starting_code,
                value_divider=value_divider,
                restricted_digit_set=restricted_digit_set,
            )

            results["success"].append(f"Row {row_num}: Device '{serial_number}' created successfully")

        except Exception as e:
            results["errors"].append(f"Row {row_num}: {str(e)}")

    # Render results template
    return render_template(
        "upload_results.html",
        success_messages=results["success"],
        skipped_messages=results["skipped"],
        error_messages=results["errors"],
    )
