import json
from pathlib import Path
import tkinter as tk
from tkinter import filedialog, messagebox

from elasticsearch import Elasticsearch
from elasticsearch.helpers import bulk


def select_log_file():
    root = tk.Tk()
    root.withdraw()

    selected_file = filedialog.askopenfilename(
        parent=root,
        title="Select the generated application logs",
        filetypes=[
            ("NDJSON file", "*.ndjson"),
            ("All files", "*.*"),
        ],
    )

    root.destroy()

    if not selected_file:
        raise SystemExit(
            "No log file selected. Import cancelled."
        )

    return Path(selected_file)


def confirm_index_replacement():
    root = tk.Tk()
    root.withdraw()

    confirmed = messagebox.askyesno(
        parent=root,
        title="Replace existing Elasticsearch index?",
        message=(
            f"The existing index '{INDEX_NAME}' will be "
            "deleted and recreated. Continue?"
        ),
    )

    root.destroy()

    return confirmed


def validate_log_file(log_path):
    try:
        with open(
            log_path,
            "r",
            encoding="utf-8"
        ) as file:

            first_document = None

            for line in file:
                if line.strip():
                    first_document = json.loads(line)
                    break

    except (OSError, json.JSONDecodeError) as error:
        raise SystemExit(
            "The selected file is not a valid NDJSON log file."
        ) from error

    if first_document is None:
        raise SystemExit(
            "The selected log file is empty."
        )

    if not isinstance(first_document, dict):
        raise SystemExit(
            "The selected file is not a valid NDJSON log file."
        )

    required_fields = {
        "@timestamp",
        "correlation_id",
        "service",
    }

    missing_fields = (
        required_fields
        - set(first_document)
    )

    if missing_fields:
        missing = ", ".join(
            sorted(missing_fields)
        )

        raise SystemExit(
            "The selected file does not contain the expected "
            f"log fields. Missing: {missing}"
        )


LOG_PATH = select_log_file()
validate_log_file(LOG_PATH)

INDEX_NAME = (
    "teleservices-logs-2026.08"
)


# ============================================================
# CONNECT
# ============================================================

print(
    "Connecting to Elasticsearch..."
)

es = Elasticsearch(
    "http://localhost:9200"
)

info = es.info()

print(
    "Connected."
)

print(
    "Elasticsearch version:",
    info["version"]["number"]
)


# ============================================================
# DELETE PREVIOUS LAB INDEX
# ============================================================

if es.indices.exists(
    index=INDEX_NAME
):

    if not confirm_index_replacement():
        raise SystemExit(
            "Import cancelled. The existing index was not changed."
        )

    print(
        "Deleting previous index..."
    )

    es.indices.delete(
        index=INDEX_NAME
    )


# ============================================================
# CREATE INDEX + FIELD TYPES
# ============================================================

print(
    "Creating index..."
)

es.indices.create(

    index=INDEX_NAME,

    mappings={

        "properties": {

            "@timestamp": {
                "type": "date"
            },

            "environment": {
                "type": "keyword"
            },

            "request_id": {
                "type": "integer"
            },

            "correlation_id": {
                "type": "keyword"
            },

            "vehicle_id": {
                "type": "keyword"
            },

            "market": {
                "type": "keyword"
            },

            "software_version": {
                "type": "keyword"
            },

            "service": {
                "type": "keyword"
            },

            "component": {
                "type": "keyword"
            },

            "level": {
                "type": "keyword"
            },

            "message": {
                "type": "text"
            },

            "http_method": {
                "type": "keyword"
            },

            "endpoint": {
                "type": "keyword"
            },

            "http_status": {
                "type": "integer"
            },

            "upstream_http_status": {
                "type": "integer"
            },

            "error_code": {
                "type": "keyword"
            },

            "latency_ms": {
                "type": "integer"
            }
        }
    }
)


# ============================================================
# STREAM DOCUMENTS
# ============================================================

def actions():

    with open(
        LOG_PATH,
        "r",
        encoding="utf-8"
    ) as file:

        for line in file:

            document = json.loads(
                line
            )

            yield {
                "_index":
                    INDEX_NAME,

                "_source":
                    document
            }


# ============================================================
# BULK INDEX
# ============================================================

print(
    "Loading log documents..."
)

success, errors = bulk(
    es,
    actions(),
    stats_only=True,
    chunk_size=1000,
    request_timeout=60
)


# Make newly indexed docs immediately searchable
es.indices.refresh(
    index=INDEX_NAME
)


print()
print(
    "Import complete."
)

print(
    f"Documents indexed: {success}"
)

print(
    f"Failed documents: {errors}"
)


# ============================================================
# VERIFY
# ============================================================

result = es.count(
    index=INDEX_NAME
)

print(
    f"Documents in index: "
    f"{result['count']}"
)
