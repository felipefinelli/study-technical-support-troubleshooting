# Lab Setup

To recreate the lab environment, you will need:

- **Python** to run the project scripts.
- **Docker Desktop** to run Elasticsearch and Kibana using the provided `docker-compose.yml`.
- **DBeaver** or another SQLite-compatible tool to access the database.

Set up the environment in this order:

1. Run `generate_database.py` to generate the database.
2. Run `generate_logs.py` and select the generated database.
3. Start Elasticsearch and Kibana using the provided `docker-compose.yml`.
4. Install the Python package required by `load_logs.py`:

```text
pip install elasticsearch
```

5. Run `load_logs.py` and select the generated logs.
6. Use DBeaver to explore the database and Kibana to explore the logs.