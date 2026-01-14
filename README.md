# OpenPAYGO Docker

A Dockerized Flask application for managing OpenPAYGO devices, generating tokens, and handling credit updates. It uses the OpenPAYGO Python library and exposes a PaygOps compatible Device API for OpenPAYGO devices. 

## Prerequisites

- Docker installed on your system
- (Optional) PostgreSQL database for production use

## Environment Variables Setup

1. Copy the example environment file:
   ```bash
   cp example.env .env
   ```

2. Edit `.env` and configure the following variables:

   ### API Authentication
   - `API_BEARER_TOKEN`: Bearer token for API authentication. Leave empty to disable authentication (for development only).

   ### CSV Upload Interface Credentials
   - `CSV_UPLOAD_USERNAME`: Username for the CSV upload web interface (default: `admin`)
   - `CSV_UPLOAD_PASSWORD`: Password for the CSV upload web interface (default: `admin`)

   ### Database Configuration

   **For SQLite (default, for development):**
   - `DB_PROVIDER`: Set to `sqlite` or leave unset
   - `SQLITE_FILE`: Path to SQLite database file (default: `openpaygo.db`)

   **For PostgreSQL (recommended for production):**
   - `DB_PROVIDER`: Set to `postgres`
   - `DB_HOST`: PostgreSQL host (default: `localhost`)
   - `DB_USER`: PostgreSQL username (default: `postgres`)
   - `DB_PASSWORD`: PostgreSQL password
   - `DB_NAME`: Database name (default: `openpaygo`)

   Example `.env` file:
   ```env
   API_BEARER_TOKEN=your-secure-api-token-here
   CSV_UPLOAD_USERNAME=admin
   CSV_UPLOAD_PASSWORD=your-secure-password
   DB_PROVIDER=postgres
   DB_HOST=localhost
   DB_USER=postgres
   DB_PASSWORD=your-db-password
   DB_NAME=openpaygo
   ```

## Running with Docker

### Build the Docker Image

```bash
make build
```

Or manually:
```bash
docker build -t openpaygo-docker .
```

### Run the Container

**Interactive mode (foreground):**
```bash
make up
```

Or manually:
```bash
docker run --rm -p 5001:8000 --env-file .env --name openpaygo-docker openpaygo-docker
```

**Daemon mode (background):**
```bash
make up_daemon
```

Or manually:
```bash
docker run -d -p 5001:8000 --env-file .env --name openpaygo-docker openpaygo-docker
```

The application will be available at `http://localhost:5001`

### Stop the Container (if running in daemon mode)

```bash
docker stop openpaygo-docker
```

## Database Connection

### SQLite (Default)

By default, the application uses SQLite, which stores data in a file. The database file is created automatically when the container starts. If using SQLite, the database file will be stored inside the container.

To persist SQLite data across container restarts, mount a volume:
```bash
docker run --rm -p 5001:8000 --env-file .env -v $(pwd)/data:/app/data --name openpaygo-docker openpaygo-docker
```

Then set `SQLITE_FILE=/app/data/openpaygo.db` in your `.env` file.

### PostgreSQL

1. Ensure PostgreSQL is running and accessible
2. Create a database (if it doesn't exist):
   ```sql
   CREATE DATABASE openpaygo;
   ```
3. Configure the database connection in your `.env` file as shown above
4. The application will automatically create the necessary tables on first run

**Note:** If running PostgreSQL in Docker, ensure the database container is on the same network or use the host's IP address.

## Uploading Devices

### Using the Web Interface

1. Start the application (see "Running with Docker" above)
2. Navigate to `http://localhost:5001/upload-devices` in your browser
3. Log in using the credentials configured in `CSV_UPLOAD_USERNAME` and `CSV_UPLOAD_PASSWORD`
4. Upload a CSV file with the following columns (case-insensitive):
   - **Serial Number**: Unique device identifier
   - **Starting Code**: Starting code/seed for token generation
   - **Key**: 32-hex-character OpenPAYGO secret key
   - **Count**: Token count
   - **Time Divider**: Value divider for token generation
   - **Restricted Digit Mode**: Whether to use restricted digit set (true/false)
   - **Hardware Model**: Device model name
   - **Version**: (optional, ignored)
   - **Test Code**: (optional, ignored)

The CSV upload interface will display the results of the import, including any errors or successful imports.

### Using the API

You can also upload devices programmatically using the REST API. Refer to the API documentation for endpoint details.

## Connecting to PAYGOPS

For instructions on how to connect this application to PAYGOPS, please refer to the [PAYGOPS documentation](https://paygops.com/documentation).

## Testing

Run the test suite:

```bash
make test
```

Or manually:
```bash
docker run --rm openpaygo-docker pytest tests/
```


