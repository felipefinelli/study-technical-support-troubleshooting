import sqlite3
import json
from datetime import datetime, timedelta, timezone
from pathlib import Path
import tkinter as tk
from tkinter import filedialog


def select_database():
    root = tk.Tk()
    root.withdraw()

    selected_file = filedialog.askopenfilename(
        parent=root,
        title=(
            "Select the generated automotive database"
        ),
        filetypes=[
            ("SQLite database", "*.db"),
            ("All files", "*.*"),
        ],
    )

    root.destroy()

    if not selected_file:
        raise SystemExit(
            "No database selected. Log generation cancelled."
        )

    return Path(selected_file)


def select_output_file(database_path):
    root = tk.Tk()
    root.withdraw()

    selected_file = filedialog.asksaveasfilename(
        parent=root,
        title="Choose where to save the generated logs",
        initialdir=database_path.parent,
        initialfile="teleservices.ndjson",
        defaultextension=".ndjson",
        filetypes=[
            ("NDJSON file", "*.ndjson"),
            ("All files", "*.*"),
        ],
    )

    root.destroy()

    if not selected_file:
        raise SystemExit(
            "No output file selected. Log generation cancelled."
        )

    return Path(selected_file)


def validate_database(cursor):
    required_tables = {
        "vehicles",
        "service_requests",
    }

    try:
        cursor.execute("""
        SELECT name
        FROM sqlite_master
        WHERE type = 'table'
        """)
    except sqlite3.DatabaseError as error:
        raise SystemExit(
            "The selected file is not a valid SQLite database."
        ) from error

    existing_tables = {
        row[0]
        for row in cursor.fetchall()
    }

    missing_tables = (
        required_tables
        - existing_tables
    )

    if missing_tables:
        missing = ", ".join(
            sorted(missing_tables)
        )

        raise SystemExit(
            "The selected file is not a valid automotive "
            f"database. Missing tables: {missing}"
        )


DB_PATH = select_database()
OUTPUT_PATH = select_output_file(DB_PATH)


SERVICE_COMPONENTS = {
    "remote_vehicle_status": "vehicle-status-service",
    "maintenance": "maintenance-service",
    "navigation": "navigation-service",
    "vehicle_location": "location-service",
}


def timestamp_with_offset(
    timestamp,
    milliseconds=0
):
    """
    Database timestamps in this lab are treated as UTC.
    """

    dt = datetime.fromisoformat(timestamp)

    dt = dt.replace(
        tzinfo=timezone.utc
    )

    dt += timedelta(
        milliseconds=milliseconds
    )

    return (
        dt.isoformat()
        .replace("+00:00", "Z")
    )


def write_event(
    file,
    event
):
    file.write(
        json.dumps(event) + "\n"
    )


def base_event(
    request_id,
    correlation_id,
    vehicle_id,
    market,
    software_version,
    service
):

    return {
        "environment": "production",
        "request_id": request_id,
        "correlation_id": correlation_id,
        "vehicle_id": vehicle_id,
        "market": market,
        "software_version": software_version,
        "service": service,
    }


conn = sqlite3.connect(DB_PATH)

cursor = conn.cursor()

validate_database(cursor)

cursor.execute("""
SELECT
    sr.request_id,
    sr.correlation_id,
    sr.vehicle_id,
    v.market,
    v.software_version,
    sr.service,
    sr.requested_at,
    sr.endpoint,
    sr.http_method,
    sr.http_status,
    sr.error_code,
    sr.latency_ms

FROM service_requests sr

JOIN vehicles v
    ON v.vehicle_id = sr.vehicle_id

ORDER BY sr.requested_at
""")

requests = cursor.fetchall()

print(
    f"Generating traces for "
    f"{len(requests)} requests..."
)

event_count = 0


with open(
    OUTPUT_PATH,
    "w",
    encoding="utf-8"
) as file:

    for row in requests:

        (
            request_id,
            correlation_id,
            vehicle_id,
            market,
            software_version,
            service,
            requested_at,
            endpoint,
            http_method,
            http_status,
            error_code,
            latency_ms
        ) = row


        common = base_event(
            request_id,
            correlation_id,
            vehicle_id,
            market,
            software_version,
            service
        )

        component = SERVICE_COMPONENTS[
            service
        ]


        # ====================================================
        # API GATEWAY
        # ====================================================

        write_event(
            file,
            {
                **common,

                "@timestamp":
                    timestamp_with_offset(
                        requested_at,
                        0
                    ),

                "component":
                    "api-gateway",

                "level":
                    "INFO",

                "message":
                    "Incoming request received",

                "http_method":
                    http_method,

                "endpoint":
                    endpoint,
            }
        )

        event_count += 1


        # ====================================================
        # SERVICE
        # ====================================================

        service_message = (
            "Request processing started"
        )

        if service == "navigation":
            service_message = (
                "Route calculation started"
            )

        elif service == "remote_vehicle_status":
            service_message = (
                "Vehicle status retrieval started"
            )

        elif service == "maintenance":
            service_message = (
                "Maintenance data retrieval started"
            )

        elif service == "vehicle_location":
            service_message = (
                "Vehicle location retrieval started"
            )


        write_event(
            file,
            {
                **common,

                "@timestamp":
                    timestamp_with_offset(
                        requested_at,
                        15
                    ),

                "component":
                    component,

                "level":
                    "INFO",

                "message":
                    service_message,
            }
        )

        event_count += 1


        # ====================================================
        # NAVIGATION
        # ====================================================

        if service == "navigation":

            write_event(
                file,
                {
                    **common,

                    "@timestamp":
                        timestamp_with_offset(
                            requested_at,
                            35
                        ),

                    "component":
                        "maps-adapter",

                    "level":
                        "INFO",

                    "message":
                        "Calling external routing provider",
                }
            )

            event_count += 1


            # -----------------------------------------------
            # Routing provider problem
            # -----------------------------------------------

            if (
                http_status == 502
                and
                error_code
                == "ROUTING_PROVIDER_ERROR"
            ):

                write_event(
                    file,
                    {
                        **common,

                        "@timestamp":
                            timestamp_with_offset(
                                requested_at,
                                max(
                                    latency_ms - 80,
                                    100
                                )
                            ),

                        "component":
                            "external-routing-provider",

                        "level":
                            "WARN",

                        "message":
                            "Routing provider rejected request",

                        "http_status":
                            429,

                        "error_code":
                            "RATE_LIMITED",
                    }
                )

                event_count += 1


                write_event(
                    file,
                    {
                        **common,

                        "@timestamp":
                            timestamp_with_offset(
                                requested_at,
                                max(
                                    latency_ms - 40,
                                    150
                                )
                            ),

                        "component":
                            "maps-adapter",

                        "level":
                            "ERROR",

                        "message":
                            "External routing provider request failed",

                        "upstream_http_status":
                            429,
                    }
                )

                event_count += 1


                write_event(
                    file,
                    {
                        **common,

                        "@timestamp":
                            timestamp_with_offset(
                                requested_at,
                                latency_ms
                            ),

                        "component":
                            "navigation-service",

                        "level":
                            "ERROR",

                        "message":
                            "Route calculation failed",

                        "http_status":
                            502,

                        "error_code":
                            error_code,

                        "latency_ms":
                            latency_ms,
                    }
                )

                event_count += 1


            # -----------------------------------------------
            # Successful navigation
            # -----------------------------------------------

            elif http_status < 400:

                write_event(
                    file,
                    {
                        **common,

                        "@timestamp":
                            timestamp_with_offset(
                                requested_at,
                                max(
                                    latency_ms - 30,
                                    60
                                )
                            ),

                        "component":
                            "maps-adapter",

                        "level":
                            "INFO",

                        "message":
                            "Route successfully received from provider",
                    }
                )

                event_count += 1


                write_event(
                    file,
                    {
                        **common,

                        "@timestamp":
                            timestamp_with_offset(
                                requested_at,
                                latency_ms
                            ),

                        "component":
                            component,

                        "level":
                            "INFO",

                        "message":
                            "Route calculation completed",

                        "http_status":
                            http_status,

                        "latency_ms":
                            latency_ms,
                    }
                )

                event_count += 1


        # ====================================================
        # BACKEND TIMEOUT
        # ====================================================

        elif http_status == 504:

            write_event(
                file,
                {
                    **common,

                    "@timestamp":
                        timestamp_with_offset(
                            requested_at,
                            45
                        ),

                    "component":
                        "vehicle-data-adapter",

                    "level":
                        "INFO",

                    "message":
                        "Requesting latest vehicle data",
                }
            )

            event_count += 1


            write_event(
                file,
                {
                    **common,

                    "@timestamp":
                        timestamp_with_offset(
                            requested_at,
                            max(
                                latency_ms - 30,
                                100
                            )
                        ),

                    "component":
                        "vehicle-data-adapter",

                    "level":
                        "WARN",

                    "message":
                        "Downstream request exceeded configured timeout",
                }
            )

            event_count += 1


            write_event(
                file,
                {
                    **common,

                    "@timestamp":
                        timestamp_with_offset(
                            requested_at,
                            latency_ms
                        ),

                    "component":
                        component,

                    "level":
                        "ERROR",

                    "message":
                        "Request failed",

                    "http_status":
                        http_status,

                    "error_code":
                        error_code,

                    "latency_ms":
                        latency_ms,
                }
            )

            event_count += 1


        # ====================================================
        # 403
        # ====================================================

        elif http_status == 403:

            write_event(
                file,
                {
                    **common,

                    "@timestamp":
                        timestamp_with_offset(
                            requested_at,
                            45
                        ),

                    "component":
                        "authorization-service",

                    "level":
                        "WARN",

                    "message":
                        "Permission check rejected request",
                }
            )

            event_count += 1


            write_event(
                file,
                {
                    **common,

                    "@timestamp":
                        timestamp_with_offset(
                            requested_at,
                            latency_ms
                        ),

                    "component":
                        component,

                    "level":
                        "ERROR",

                    "message":
                        "Request failed",

                    "http_status":
                        http_status,

                    "error_code":
                        error_code,

                    "latency_ms":
                        latency_ms,
                }
            )

            event_count += 1


        # ====================================================
        # 404
        # ====================================================

        elif http_status == 404:

            write_event(
                file,
                {
                    **common,

                    "@timestamp":
                        timestamp_with_offset(
                            requested_at,
                            45
                        ),

                    "component":
                        "vehicle-registry",

                    "level":
                        "WARN",

                    "message":
                        "Vehicle record could not be resolved",
                }
            )

            event_count += 1


            write_event(
                file,
                {
                    **common,

                    "@timestamp":
                        timestamp_with_offset(
                            requested_at,
                            latency_ms
                        ),

                    "component":
                        component,

                    "level":
                        "ERROR",

                    "message":
                        "Request failed",

                    "http_status":
                        http_status,

                    "error_code":
                        error_code,

                    "latency_ms":
                        latency_ms,
                }
            )

            event_count += 1


        # ====================================================
        # GENERIC 500
        # ====================================================

        elif http_status >= 500:

            write_event(
                file,
                {
                    **common,

                    "@timestamp":
                        timestamp_with_offset(
                            requested_at,
                            latency_ms
                        ),

                    "component":
                        component,

                    "level":
                        "ERROR",

                    "message":
                        "Unexpected service error",

                    "http_status":
                        http_status,

                    "error_code":
                        error_code,

                    "latency_ms":
                        latency_ms,
                }
            )

            event_count += 1


        # ====================================================
        # NORMAL SUCCESS
        # ====================================================

        elif http_status < 400:

            write_event(
                file,
                {
                    **common,

                    "@timestamp":
                        timestamp_with_offset(
                            requested_at,
                            latency_ms
                        ),

                    "component":
                        component,

                    "level":
                        "INFO",

                    "message":
                        "Request completed successfully",

                    "http_status":
                        http_status,

                    "latency_ms":
                        latency_ms,
                }
            )

            event_count += 1


        # ====================================================
        # API GATEWAY RESPONSE
        # ====================================================

        write_event(
            file,
            {
                **common,

                "@timestamp":
                    timestamp_with_offset(
                        requested_at,
                        latency_ms + 5
                    ),

                "component":
                    "api-gateway",

                "level":
                    "INFO",

                "message":
                    "Response returned to client",

                "http_status":
                    http_status,

                "latency_ms":
                    latency_ms,
            }
        )

        event_count += 1


conn.close()

print()
print("Log generation complete.")
print(
    f"Requests processed: {len(requests)}"
)
print(
    f"Log events created: {event_count}"
)
print(
    f"Output: {OUTPUT_PATH}"
)
