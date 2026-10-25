# Stage 5 risk, driver and graph method

## Driver analysis

The analyst endpoint compares a caller-selected set of affected canonical record references with the remaining rows from the same source only. It considers supplier, carrier, product, region, mode and ISO week when those fields are mapped and present. Each group reports affected and baseline support, affected-rate difference (risk difference), a two-sided Fisher exact test, and a Benjamini-Hochberg adjusted p-value. Groups below the configured support are omitted. A result is marked as a statistically supported association only when configured support, adjusted p-value and absolute effect-size conditions all pass. It remains an `UNVERIFIED` hypothesis; the interpretation is always **correlation, not proof**.

The change-point estimate scans ordered ISO weeks and selects the boundary with the largest absolute difference in affected rates, subject to minimum segment size. It is descriptive and is not evidence of a causal event. Defaults are in `config/settings.yaml` under `driver_analysis`; no driver threshold is embedded in the route.

Driver evidence references identify affected rows in the selected group and affected rows outside it. The latter are contradictory observations for that group. Missing evidence explicitly calls for independent validation and evidence of a mechanism. This is a screen for further review, not a causal discovery method.

## Risk prioritization

Risk input is kept in four separate factor fields: calibrated likelihood, impact, evidence strength and uncertainty. Likelihood is omitted unless the caller explicitly marks it calibrated. Company administrators can save immutable scoring-config versions through `/api/v1/risk/scoring-config`; the stored version and its factor weights/thresholds are returned with each score. Only calibrated likelihood together with impact permits an aggregate numeric score and severity. Otherwise the response has no aggregate numeric score or severity and returns a qualitative `HIGHLY_UNCERTAIN` or `QUALITATIVE_REVIEW` rating. A defensible numeric score is a prioritization aid and does not establish cause or authorize action.

Default company weights and severity thresholds are specified in `config/settings.yaml` under `company_risk_scoring`. Older generic factor settings remain available in the same file for the existing priority engine. The Stage 5 company configuration is persisted with company ownership and configuration history in SQLite; it can be moved to another SQLAlchemy backend by configuration.

## Hypothesis lifecycle and presentation labels

Persisted status values remain `UNVERIFIED`, `SUPPORTED`, `CONFIRMED`, `REJECTED`, and `CLOSED`. Human-facing API `status_label` values are `Unverified`, `Supported by evidence`, `Human confirmed`, `Rejected`, and `Closed`. Labels do not alter status. Only the existing reviewer-role confirmation operation may set `CONFIRMED`, with its required review rationale and history.

## Graph construction and analytics

Graph records are read only from completed imports with an accepted mapping. Entity identifiers are namespaced by source; matching identifiers in separate sources do not create a connection. Edges generated from mapped co-occurrence carry the source-record reference, source name, mapping-version and source-hash provenance, validity interval, meaning, and `ESTABLISHED` flag. Analyst-proposed user links remain pending until a reviewer approves them and then carry `USER_ENTERED`. Incident-to-record associations carry `INFERRED` and cannot be used as a confirmed-cause claim.

Downstream exposure and upstream trace traverse `ESTABLISHED` edges only. Supplier concentration, single-source product dependencies, downstream order exposure, and incident counts against supplier peer averages are labelled exposure or hypothesis. Node categories with no mapped values are returned in `omitted_node_types`. No cross-source edge is created unless the user explicitly proposes it and a reviewer approves it.

## Limitations

- Results depend on approved mappings and complete source-record references.
- Driver analysis is observational; confounding, selection and repeated testing remain possible despite multiple-comparison correction.
- Graph edges represent recorded relationships, not a causal mechanism.
- A numeric delay likelihood is usable only when separately calibrated and supplied as such.
