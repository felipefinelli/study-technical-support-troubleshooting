# Automotive Technical Support Lab

In this project, I tried to simulate, in a very simplified way, technical support troubleshooting in an automotive digital services context.

Incidents are initially received as descriptive reports, as they might be received through an incident management tool such as Jira.

## Troubleshooting Environment

The troubleshooting environment includes:

- **Operational database** — contains information about vehicles, markets, software versions, and requests made to different digital services. SQL through DBeaver is used to search and analyze this data.
- **Elasticsearch + Kibana** — used to explore application logs and follow individual requests through different system components. A `correlation_id` allows a request found in the database to be connected to its corresponding logs.

The environment runs locally using Docker for Elasticsearch and Kibana. I generated the database and application logs through Python scripts with AI assistance.

## Troubleshooting Scenarios

### Incident 01 — Online Navigation

Investigating a reported problem affecting Online Navigation for users in Italy.

[View investigation](./incidents/incident-01-online-navigation/)

### Incident 02 — Vehicle Status

Investigating intermittent problems when retrieving vehicle status information.

[View investigation](./incidents/incident-02-vehicle-status/)

## Project Structure

```text
automotive-support-lab/
│
├── README.md
│
├── database/
│   ├── automotive.db              # Database used in the troubleshooting scenarios
│   └── generate_database.py       # Python script used to create the database
│
├── elasticsearch-kibana/
│   ├── docker-compose.yml         # Starts Elasticsearch and Kibana with Docker
│   ├── generate_logs.py           # Python script used to generate the logs
│   ├── load_logs.py               # Python script used to load the logs into Elasticsearch
│   └── teleservices.ndjson        # File containing the generated logs
│
├── incidents/
│   ├── incident-01-online-navigation/
│   │   └── README.md              # Step-by-step investigation of Incident 01
│   │
│   └── incident-02-vehicle-status/
│       └── README.md              # Step-by-step investigation of Incident 02
│
└── setup/
    └── README.md                  # Basic instructions for recreating the lab environment
```

## Recreate the Lab Environment

Everything needed to recreate the local lab environment is available in the [`setup`](./setup/) folder.
