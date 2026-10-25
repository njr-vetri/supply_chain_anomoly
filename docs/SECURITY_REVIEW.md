# Phase 10 security review

## Dependency audit

Commands run:

```powershell
pip-audit --no-deps --disable-pip --timeout 5 --progress-spinner off -r requirements.lock -r requirements-dev.lock
```

The initial advisory check flagged `pytest 9.0.2`, `python-dotenv 1.2.1`, and `starlette 0.41.3` (the FastAPI-pinned version). They were upgraded to `pytest 9.1.1`, `python-dotenv 1.2.4`, and `fastapi 0.161.1` / `starlette 1.9.0`; both lock files were regenerated. The repeat audit reported **No known vulnerabilities found** for the pinned runtime and development lock entries. `--no-deps` was used because all transitive dependencies are explicitly present in the locks; pip-audit warned that hash-pinned requirements are preferable. Hashes were not added in this phase.

GPU-only optional packages from `requirements-gpu.txt` are not part of either CPU lock and were not audited in the final command. Audit results reflect the advisory data reachable on the audit date and are not a guarantee that dependencies are safe.

## Secrets and logging

- `python scripts/security_scan.py` reported no matches. This is a local heuristic scan, not an exhaustive secret detector. The scanner omits ignored data/model directories and `.env.example`; it never prints matched values.
- Alert console/file output, alert history, and audit details now use shared key-name and common email/phone pattern redaction. API request bodies and API keys are not written to application logs. Redaction can miss unfamiliar PII and can redact benign numeric text.
- The `.env` file remains ignored by Git and Docker build context. `.env.example` contains only a replacement placeholder.

## Input validation and action boundary

- API request models reject extra fields and constrain body sizes, identifiers, action classes, dataset names, and free-text lengths. Path identifiers are bounded. Request validation errors use the API's normalized error object.
- Inbound text remains inert data. The action endpoint accepts an enum-like fixed action class and an existing recommendation reference; it does not execute free-text instructions.
- High-impact action records require an approved approval record; the API still records actions as `DRY_RUN`. Admin-only kill-switch routes and reviewer-only hypothesis confirmation are covered by TestClient checks.
- API CORS allows only configured origins and does not enable credential cookies. Local key-to-role mapping is not an identity provider.

## Findings not resolved or checks not performed

- Simple local API-key storage/rotation, TLS, stronger identity, rate limiting under load, and deployment threat modeling remain outside scope. This project is not production-ready.
- The process-local API kill switch resets on restart. YAML only supplies the startup default.
- PII redaction is heuristic and does not replace privacy review or a retention policy.
- Hash-chained audit files detect edits but do not prevent filesystem-level deletion or replacement.
- The workspace has no `.git` directory, so the pre-commit hook could not be installed or run against a real staged index without initializing a repository. `AGENTS.md` prohibits running `git init`; the guard logic was unit-tested with synthetic paths, and its explicit-path CLI passed on safe paths.
- Docker and Docker Compose executables were not available in this workspace, so the image was not built or started. YAML parsing can be checked locally; runtime container behavior remains unverified.
- No GitHub connection or remote workflow execution was made. The workflow file is local configuration only.
