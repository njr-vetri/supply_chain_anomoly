# Delay label definitions and leakage inspection

## Olist review text labels (Phase 7B)

- **Purpose:** three-class review-text classifier using Olist `review_score` as a proxy label. Scores 1–2 map to `complaint`, 3 maps to `neutral`, and 4–5 map to `positive`.
- **Limits:** these are score bands from the dataset, not human-annotated sentiment, complaint type, delivery cause, or proof that the review text expresses the score. Do not interpret a predicted label as a verified fact.
- **Eligibility:** rows with a valid score, review creation timestamp, and non-empty title/comment text are included. Empty-text rows are excluded because the text classifier has no input.
- **Split:** stable chronological 60/20/20 train/validation/test split by `review_creation_date`; all reported holdout metrics are computed on the final 20% only when the required runtime dependencies are available.

Input review text is untrusted data. Cleaning, regex PII redaction, language heuristics, and extraction do not interpret instructions or trigger actions.

## Olist

- **Label:** `delayed = 1` when `order_delivered_customer_date` is later than `order_estimated_delivery_date`; otherwise `0`.
- **Eligible records:** retain only orders with both timestamps and `order_status == delivered`. Canceled, unavailable, or undelivered orders do not have an observed delivery-delay label and are excluded from supervised evaluation.
- **Prediction time:** order purchase time. Features must be available then. `order_estimated_delivery_date` is only usable if assigned by purchase; this assumption needs source/process verification. Historical seller statistics may use only earlier completed orders.
- **Excluded predictors:** actual delivery/carrier timestamps, actual delivery duration, deviation, reviews, and any post-purchase fields.

## DataCo

- **Label:** the audited `Late_delivery_risk` value, treated as the dataset's recorded binary target (`1` = risk/late, `0` = not flagged). This is a dataset label, not an independently verified operational truth.
- **Time split:** chronological by audited `order date (DateOrders)`.
- **Excluded predictors from leakage inspection:** `Late_delivery_risk` (target itself); `Delivery Status` (direct textual outcome category); `Days for shipping (real)` (realized outcome); `shipping date (DateOrders)` (post-order event); and any delivery timestamp, late/delay outcome alias, or target-derived field. These are not passed to model features.
- **Allowed model inputs:** `Days for shipment (scheduled)`, `Shipping Mode`, order timestamp/calendar parts, and `Order Region`, subject to confirmation that those fields are known at the intended decision time. Customer PII and free-text access logs are excluded.
- The target's exact construction could not be independently proven from the structural audit. Results, if produced, must be interpreted as reproducing this field, not establishing causal risk or prospective accuracy.

## Demand forecasting (UCI Online Retail II)

Target is weekly transaction quantity aggregated by `StockCode`; this is a demand forecast. It is not a stockout or inventory prediction. Forecast validation is rolling-origin/time-series only. Cancellations/negative quantities remain as observed transaction records unless a later documented policy changes that definition.
