import sqlite3
import random
import uuid
import hashlib
from datetime import datetime, timedelta
from pathlib import Path


# ============================================================
# CONFIG
# ============================================================

random.seed(42)

BASE_DIR = Path(__file__).resolve().parent
DB_PATH = BASE_DIR / "automotive.db"

NUM_VEHICLES = 500
NUM_REQUESTS = 30000

MARKETS = ["DE", "PT", "ES", "FR", "IT"]

SERVICES = [
    "remote_vehicle_status",
    "maintenance",
    "navigation",
    "vehicle_location",
]

SOFTWARE_VERSIONS = [
    "4.1.0",
    "4.2.0",
    "4.2.1",
    "5.0.0",
]

MODELS = [
    "Model-A",
    "Model-B",
    "Model-C",
    "Model-D",
]


# ============================================================
# DATABASE
# ============================================================

conn = sqlite3.connect(DB_PATH)
cursor = conn.cursor()

cursor.executescript("""
DROP TABLE IF EXISTS service_requests;
DROP TABLE IF EXISTS market_configuration;
DROP TABLE IF EXISTS vehicles;
""")


# ============================================================
# TABLES
# ============================================================

cursor.execute("""
CREATE TABLE vehicles (
    vehicle_id TEXT PRIMARY KEY,
    manufacturer TEXT NOT NULL,
    model TEXT NOT NULL,
    model_year INTEGER NOT NULL,
    market TEXT NOT NULL,
    software_version TEXT NOT NULL,
    last_seen_at TEXT NOT NULL
)
""")


cursor.execute("""
CREATE TABLE service_requests (
    request_id INTEGER PRIMARY KEY AUTOINCREMENT,
    correlation_id TEXT NOT NULL UNIQUE,
    vehicle_id TEXT NOT NULL,
    service TEXT NOT NULL,
    requested_at TEXT NOT NULL,
    endpoint TEXT NOT NULL,
    http_method TEXT NOT NULL,
    http_status INTEGER NOT NULL,
    error_code TEXT,
    latency_ms INTEGER NOT NULL,

    FOREIGN KEY(vehicle_id)
        REFERENCES vehicles(vehicle_id)
)
""")


cursor.execute("""
CREATE TABLE market_configuration (
    market TEXT NOT NULL,
    service TEXT NOT NULL,
    enabled INTEGER NOT NULL,
    endpoint_version TEXT NOT NULL,
    configuration_version TEXT NOT NULL,
    updated_at TEXT NOT NULL,

    PRIMARY KEY (market, service)
)
""")


# ============================================================
# VEHICLES
# ============================================================

vehicles = []

for i in range(1, NUM_VEHICLES + 1):

    vehicle_id = f"VEH-{i:04d}"

    market = random.choice(MARKETS)
    software_version = random.choice(SOFTWARE_VERSIONS)
    model = random.choice(MODELS)
    model_year = random.randint(2021, 2026)

    last_seen = datetime(2026, 8, 1) + timedelta(
        days=random.randint(0, 17),
        hours=random.randint(0, 23),
        minutes=random.randint(0, 59)
    )

    vehicles.append([
        vehicle_id,
        "Example Motors",
        model,
        model_year,
        market,
        software_version,
        last_seen
    ])


# ------------------------------------------------------------
# Alguns veículos precisam ter características determinísticas
# para que nossos incidentes sejam reproduzíveis.
# ------------------------------------------------------------

for vehicle in vehicles:

    vehicle_id = vehicle[0]

    # INC-78342 example vehicle
    if vehicle_id == "VEH-0092":
        vehicle[4] = "IT"
        vehicle[5] = "4.2.0"

    # Example vehicles associated with INC-48217
    if vehicle_id in {
        "VEH-0187",
        "VEH-0312",
        "VEH-0441"
    }:
        vehicle[4] = "DE"


cursor.executemany("""
INSERT INTO vehicles (
    vehicle_id,
    manufacturer,
    model,
    model_year,
    market,
    software_version,
    last_seen_at
)
VALUES (?, ?, ?, ?, ?, ?, ?)
""", [
    (
        vehicle[0],
        vehicle[1],
        vehicle[2],
        vehicle[3],
        vehicle[4],
        vehicle[5],
        vehicle[6].isoformat()
    )
    for vehicle in vehicles
])


# ============================================================
# MARKET CONFIGURATION
# ============================================================

configuration_updated = "2026-08-01T08:00:00"

for market in MARKETS:

    for service in SERVICES:

        cursor.execute("""
        INSERT INTO market_configuration (
            market,
            service,
            enabled,
            endpoint_version,
            configuration_version,
            updated_at
        )
        VALUES (?, ?, ?, ?, ?, ?)
        """, (
            market,
            service,
            1,
            "v2",
            "2026.08",
            configuration_updated
        ))


# ============================================================
# HELPERS
# ============================================================

vehicle_lookup = {
    vehicle[0]: vehicle
    for vehicle in vehicles
}


def new_correlation_id():
    return "req-" + uuid.uuid4().hex[:16]


def hidden_incident_profile(
    market,
    software_version,
    service
):
    """
    Intentionally opaque.

    This produces one deterministic anomalous segment in the
    synthetic dataset without making the investigation answer
    obvious from reading the generator.

    Treat the generated database as the source of truth during
    the troubleshooting exercise.
    """

    value = (
        market
        + "|"
        + software_version
        + "|"
        + service
    )

    digest = hashlib.sha256(
        value.encode("utf-8")
    ).hexdigest()

    anomaly_signature = "1e707356"

    return digest.startswith(
        anomaly_signature
    )


# ============================================================
# NORMAL REQUEST GENERATION
# ============================================================

START_DATE = datetime(2026, 8, 1)
END_DATE = datetime(2026, 8, 18, 8, 30)

total_seconds = int(
    (END_DATE - START_DATE).total_seconds()
)


for _ in range(NUM_REQUESTS):

    vehicle = random.choice(vehicles)

    vehicle_id = vehicle[0]
    market = vehicle[4]
    software_version = vehicle[5]

    service = random.choice(SERVICES)

    requested_at = (
        START_DATE
        + timedelta(
            seconds=random.randint(
                0,
                total_seconds
            )
        )
    )

    endpoint = f"/api/v2/{service}"

    http_status = 200
    error_code = None
    latency_ms = random.randint(80, 450)

    # --------------------------------------------------------
    # Background production noise
    # --------------------------------------------------------

    noise_roll = random.random()

    if noise_roll < 0.006:

        http_status = 500
        error_code = "INTERNAL_ERROR"
        latency_ms = random.randint(
            300,
            1200
        )

    elif noise_roll < 0.010:

        http_status = 403
        error_code = "PERMISSION_DENIED"
        latency_ms = random.randint(
            80,
            300
        )

    elif noise_roll < 0.014:

        http_status = 404
        error_code = "VEHICLE_NOT_FOUND"
        latency_ms = random.randint(
            80,
            350
        )

    # --------------------------------------------------------
    # INC-48217
    #
    # The anomaly profile is intentionally opaque.
    # Investigate it from the generated operational data.
    # --------------------------------------------------------

    if (
        hidden_incident_profile(
            market,
            software_version,
            service
        )
        and requested_at
            >= datetime(2026, 8, 16, 6, 0)
        and random.random() < 0.34
    ):

        http_status = 504
        error_code = "BACKEND_TIMEOUT"
        latency_ms = random.randint(
            5000,
            9000
        )

    cursor.execute("""
    INSERT INTO service_requests (
        correlation_id,
        vehicle_id,
        service,
        requested_at,
        endpoint,
        http_method,
        http_status,
        error_code,
        latency_ms
    )
    VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
    """, (
        new_correlation_id(),
        vehicle_id,
        service,
        requested_at.isoformat(),
        endpoint,
        "GET",
        http_status,
        error_code,
        latency_ms
    ))
# ============================================================
# REPRODUCIBLE EXAMPLES FOR INC-48217
# ============================================================

incident_48217_examples = [
    "VEH-0187",
    "VEH-0312",
    "VEH-0441",
]

hidden_matches = []

for version in SOFTWARE_VERSIONS:
    for service in SERVICES:

        if hidden_incident_profile(
            "DE",
            version,
            service
        ):
            hidden_matches.append(
                (version, service)
            )


if len(hidden_matches) != 1:
    raise RuntimeError(
        "INC-48217 fixture configuration is invalid."
    )


hidden_version, hidden_service = hidden_matches[0]


# Ensure the reported example vehicles belong to the
# affected technical segment.
for vehicle_id in incident_48217_examples:

    cursor.execute("""
    UPDATE vehicles
    SET
        market = 'DE',
        software_version = ?
    WHERE vehicle_id = ?
    """, (
        hidden_version,
        vehicle_id
    ))


example_timestamps = [
    "2026-08-17T10:14:22",
    "2026-08-17T16:42:07",
    "2026-08-18T06:51:31",
]


for vehicle_id, timestamp in zip(
    incident_48217_examples,
    example_timestamps
):

    cursor.execute("""
    INSERT INTO service_requests (
        correlation_id,
        vehicle_id,
        service,
        requested_at,
        endpoint,
        http_method,
        http_status,
        error_code,
        latency_ms
    )
    VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
    """, (
        new_correlation_id(),
        vehicle_id,
        hidden_service,
        timestamp,
        f"/api/v2/{hidden_service}",
        "GET",
        504,
        "BACKEND_TIMEOUT",
        random.randint(5000, 9000)
    ))

# ============================================================
# INC-78342
# ONLINE NAVIGATION / ITALY
#
# This incident is intentionally easier to reproduce because
# it will be used as our guided Kibana tutorial.
# ============================================================

navigation_example_requests = [

    (
        "2026-08-12T15:28:04",
        200,
        None,
        231
    ),

    (
        "2026-08-12T15:32:17",
        200,
        None,
        255
    ),

    (
        "2026-08-12T15:38:21",
        502,
        "ROUTING_PROVIDER_ERROR",
        2940
    ),
]


for (
    timestamp,
    status,
    error,
    latency
) in navigation_example_requests:

    cursor.execute("""
    INSERT INTO service_requests (
        correlation_id,
        vehicle_id,
        service,
        requested_at,
        endpoint,
        http_method,
        http_status,
        error_code,
        latency_ms
    )
    VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
    """, (
        new_correlation_id(),
        "VEH-0092",
        "navigation",
        timestamp,
        "/api/v2/navigation",
        "GET",
        status,
        error,
        latency
    ))


# ------------------------------------------------------------
# Additional Italy navigation failures so this does not look
# like a single isolated request.
# ------------------------------------------------------------

italian_vehicles = [
    vehicle[0]
    for vehicle in vehicles
    if vehicle[4] == "IT"
]

for _ in range(45):

    vehicle_id = random.choice(
        italian_vehicles
    )

    requested_at = (
        datetime(2026, 8, 12, 14, 30)
        + timedelta(
            minutes=random.randint(
                0,
                100
            ),
            seconds=random.randint(
                0,
                59
            )
        )
    )

    cursor.execute("""
    INSERT INTO service_requests (
        correlation_id,
        vehicle_id,
        service,
        requested_at,
        endpoint,
        http_method,
        http_status,
        error_code,
        latency_ms
    )
    VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
    """, (
        new_correlation_id(),
        vehicle_id,
        "navigation",
        requested_at.isoformat(),
        "/api/v2/navigation",
        "GET",
        502,
        "ROUTING_PROVIDER_ERROR",
        random.randint(
            1800,
            4000
        )
    ))


# ============================================================
# INDEXES
# ============================================================

cursor.execute("""
CREATE INDEX
idx_service_requests_vehicle
ON service_requests(vehicle_id)
""")

cursor.execute("""
CREATE INDEX
idx_service_requests_service
ON service_requests(service)
""")

cursor.execute("""
CREATE INDEX
idx_service_requests_time
ON service_requests(requested_at)
""")

cursor.execute("""
CREATE INDEX
idx_service_requests_status
ON service_requests(http_status)
""")

cursor.execute("""
CREATE INDEX
idx_vehicles_market
ON vehicles(market)
""")


# ============================================================
# SAVE
# ============================================================

conn.commit()


# ============================================================
# BASIC VALIDATION
# ============================================================

print()
print("===================================")
print("AUTOMOTIVE SUPPORT DATABASE")
print("===================================")

cursor.execute(
    "SELECT COUNT(*) FROM vehicles"
)

print(
    "Vehicles:",
    cursor.fetchone()[0]
)


cursor.execute(
    "SELECT COUNT(*) FROM service_requests"
)

print(
    "Service requests:",
    cursor.fetchone()[0]
)


cursor.execute("""
SELECT COUNT(*)
FROM market_configuration
""")

print(
    "Market configurations:",
    cursor.fetchone()[0]
)


cursor.execute("""
SELECT
    vehicle_id,
    market,
    software_version
FROM vehicles
WHERE vehicle_id = 'VEH-0092'
""")

print()
print("INC-78342 example vehicle:")
print(
    cursor.fetchone()
)


cursor.execute("""
SELECT COUNT(*)
FROM sqlite_master
WHERE type = 'table'
AND name = 'tickets'
""")

tickets_exists = (
    cursor.fetchone()[0] > 0
)

print()
print(
    "Tickets table exists:",
    tickets_exists
)

print()
print(
    "Database:",
    DB_PATH
)

print("===================================")

conn.close()