# Local workflow operations

`src/workflow/LocalWorkflowScheduler` is a local, standard-library timer and queue. It does not start itself and it does not deploy or call cloud services. Create a scheduler with a trusted pipeline callback, call `start()` to enable periodic timer jobs, call `WorkflowEngine.poll_connector()` when a source poll is requested, and call `run_pending()` to execute queued jobs. `stop()` shuts down the timer thread. A new-batch event is idempotent by batch/source identity; timer events use an idempotency key for the scheduled time slot.

Job states are appended to a local JSONL history: `QUEUED`, `RUNNING`, `RETRYING`, `COMPLETED` or `FAILED`. Retry attempts and backoff come from `config/settings.yaml` (`workflow`). Failure records include only the exception class and a generic message. Payload fields are allow-listed; command-like and free-text fields cannot enter the workflow callback. The scheduler is for trusted ingestion/pipeline callbacks and does not execute actions.

Alerts retain their existing grouping, duplicate suppression, severity routes and configured elapsed-time escalation. `AlertManager.acknowledge()` and `.assign()` add append-only history entries and restore current group state from history on restart. Required acknowledgement reason and assignment target are recorded. The API exposes acknowledgement and assignment to analyst-role callers.

Approvals remain pending until a reviewer records approve/reject plus a reason. `HIGH_IMPACT` actions are blocked without an approved reviewer record. Operational action execution remains dry-run by default, subject to the global kill switch, idempotency, rate limits, circuit breaker and bounded retry policy. A dry-run cannot be recorded as executed.

## Outcome tracking

`record_execution_verification()` accepts an execution attempt only after the persisted action is marked executed; it rejects dry-run records and enforces recorded approval for high-impact actions. It labels the attempt `EXECUTED_VERIFIED`, `EXECUTION_UNVERIFIED` or `FAILED` and stores the structured result. `record_observed_outcome()` requires a timezone-aware timestamp, checks that linked predictions and recommendations predate it, stores the observation and compares it only with prior values explicitly recorded in those objects. Unspecified recommendation outcomes are `NOT_COMPARABLE`. No comparison establishes that an action caused the observed outcome.

Observed outcome input should contain only fields necessary for comparison. Audit events store identifiers and comparison status rather than raw observation content.
