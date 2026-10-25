# Feature catalog

Availability refers to the time a feature can be known for an intended prediction. Outcome fields are explicitly marked as post-event and must not be used as predictors for that earlier decision.

| Feature | Meaning | Source column(s) | Prediction-time availability |
|---|---|---|---|
| `estimated_transit_days` | Difference between estimated delivery and purchase timestamp | Olist `order_estimated_delivery_date`, `order_purchase_timestamp` | At order purchase, if estimate is already assigned |
| `actual_delivery_days` | Elapsed purchase-to-delivery duration | Olist `order_delivered_customer_date`, `order_purchase_timestamp` | Only after delivery; outcome/monitoring only |
| `delivery_deviation_days` | Actual duration minus estimated duration | Olist delivered and estimated dates | Only after delivery; outcome/monitoring only |
| `prior_seller_delivery_days_mean` | Mean of the seller's earlier observed delivery durations | Olist `seller_id`, `order_purchase_timestamp`, `order_delivered_customer_date` | At current order only if history is strictly earlier; null without history |
| `prior_seller_order_count` | Number of earlier seller-order observations | Olist `seller_id`, `order_purchase_timestamp` | At current order using strictly earlier timestamps |
| `scheduled_shipping_days` | Planned shipping duration | DataCo `Days for shipment (scheduled)` | At order/shipment planning, subject to source semantics |
| `shipping_mode` | Planned shipping method | DataCo `Shipping Mode` | At order/shipment planning |
| `order_timestamp`, `order_weekday` | Order time and weekday calendar value | DataCo `order date (DateOrders)` | At order time |
| `order_region` | Order destination region | DataCo `Order Region` | At order time if supplied then |
| `observed_actual_shipping_days` | Realized shipping duration | DataCo `Days for shipping (real)` | After fulfillment; outcome/monitoring only |
| `observed_late_delivery_risk` | Dataset's recorded delay label | DataCo `Late_delivery_risk` | Label only after verifying construction; never a predictor by default |
| `weekly_quantity` | Sum of transaction quantities per product-week | Retail II `StockCode`, `InvoiceDate`, `Quantity` | At end of that week; demand history only |
| `quantity_lag_1w`, `quantity_lag_2w`, `quantity_lag_4w` | Quantity from previous product-weeks | Retail II `StockCode`, `InvoiceDate`, `Quantity` | At the current week only for fully closed prior weeks |

Online Retail II features describe transaction demand. They do not represent on-hand stock or stockouts. DataCo fields require event-time verification before modeling; target leakage is possible.
