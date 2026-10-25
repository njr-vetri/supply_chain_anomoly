# Local connector architecture

Source adapters implement `SourceConnector` (`health_check()` and `read_batches()`) and produce typed `RecordBatch` values. Notification adapters implement `NotificationConnector`. They are local Python interfaces; they do not require an account or cloud database.

## Available source adapters

- **Scheduled folder:** `FolderImportConnector` reads CSV, JSON/JSONL, XLSX and CSV members inside ZIPs in configured `data/incoming`. It hashes each original and never rewrites or extracts it. CSV/JSONL and ZIP-CSV reads are chunked. ZIP entry, decompressed-size, compression-ratio and path checks reject unsafe archives. Create the incoming folder only when using this adapter.
- **REST polling:** `RestPollingConnector` polls one configured HTTP(S) endpoint and accepts a JSON object/list. Endpoint and optional bearer-token environment-variable names come from `config/settings.yaml`; secret values are read only from the environment.
- **Database import:** `DatabaseImportConnector` uses SQLAlchemy `SELECT` with streaming batches. It accepts a validated simple table identifier and a connection URL from an environment variable. SQLite is available locally; other SQLAlchemy dialects require their driver to be installed. The connector issues no writes.

`WorkflowEngine.poll_connector()` checks adapter health, reads its batches and queues idempotent `new_batch` jobs. A configured local timer can queue periodic `timer` jobs. Both operate on a caller-supplied trusted callback. Folder path, batch size, REST environment names, timeouts, database table and workflow retry/timer settings are configurable in `config/settings.yaml`.

## Notification adapters

SMTP reads `SMTP_HOST`, `SMTP_PORT`, `SMTP_USERNAME`, `SMTP_PASSWORD`, `SMTP_FROM`, `SMTP_TO`, and `SMTP_STARTTLS`. Webhook reads `WEBHOOK_URL` and optional `WEBHOOK_TOKEN`. No credentials are in code or configuration. Both adapters return `DRY_RUN` and make no notification request unless the environment variable named by `connectors.notifications_enabled_env` is set to `true` (`CONNECTORS_ENABLED` by default). Explicit health checks perform a connection/authentication check only when notifications are enabled. Injected mock transports report `SIMULATED`.

Copy `.env.example` to `.env` for local configuration. Keep the connector disabled until the endpoints and recipients have been reviewed. A notification sends serialized text only; incoming text is never parsed as an action or command.

## Extensions not built

ERP and WMS adapters are declared as `EXTENSION_NOT_IMPLEMENTED`. They require vendor-specific authentication, read-only query design, mapping approval and integration tests. No ERP/WMS connectivity is implied by the generic connectors.
