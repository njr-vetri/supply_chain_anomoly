# Dataset audit: olist

Archive: `archive (1).zip`

## Archive files

- olist_customers_dataset.csv (9,033,957 bytes uncompressed)
- olist_geolocation_dataset.csv (61,273,883 bytes uncompressed)
- olist_order_items_dataset.csv (15,438,671 bytes uncompressed)
- olist_order_payments_dataset.csv (5,777,138 bytes uncompressed)
- olist_order_reviews_dataset.csv (14,451,670 bytes uncompressed)
- olist_orders_dataset.csv (17,654,914 bytes uncompressed)
- olist_products_dataset.csv (2,379,446 bytes uncompressed)
- olist_sellers_dataset.csv (174,703 bytes uncompressed)
- product_category_name_translation.csv (2,613 bytes uncompressed)
- LIMITATIONS: Delivery timestamps and review fields may occur after purchase; exclude them from any prediction made before those events.

## Tables and sheets

### olist_customers_dataset.csv

- Rows: 99,441
- Duplicate rows: 0
- Columns:
  | Column | Dtype | Missing % |
  |---|---|---:|
  | `customer_id` | `str` | 0.0000% |
  | `customer_unique_id` | `str` | 0.0000% |
  | `customer_zip_code_prefix` | `int64` | 0.0000% |
  | `customer_city` | `str` | 0.0000% |
  | `customer_state` | `str` | 0.0000% |
- Date coverage:
  - No date-like columns with parseable values detected.
- ID uniqueness:
  - customer_id: 99,441/99,441 non-null values unique
  - customer_unique_id: 96,096/99,441 non-null values unique
  - customer_zip_code_prefix: 14,994/99,441 non-null values unique
- Candidate label columns (name-based; not validated targets): none detected

### olist_geolocation_dataset.csv

- Rows: 1,000,163
- Duplicate rows: 261,831
- Columns:
  | Column | Dtype | Missing % |
  |---|---|---:|
  | `geolocation_zip_code_prefix` | `int64` | 0.0000% |
  | `geolocation_lat` | `float64` | 0.0000% |
  | `geolocation_lng` | `float64` | 0.0000% |
  | `geolocation_city` | `str` | 0.0000% |
  | `geolocation_state` | `str` | 0.0000% |
- Date coverage:
  - No date-like columns with parseable values detected.
- ID uniqueness:
  - geolocation_zip_code_prefix: 19,015/1,000,163 non-null values unique
- Candidate label columns (name-based; not validated targets): none detected

### olist_order_items_dataset.csv

- Rows: 112,650
- Duplicate rows: 0
- Columns:
  | Column | Dtype | Missing % |
  |---|---|---:|
  | `order_id` | `str` | 0.0000% |
  | `order_item_id` | `int64` | 0.0000% |
  | `product_id` | `str` | 0.0000% |
  | `seller_id` | `str` | 0.0000% |
  | `shipping_limit_date` | `str` | 0.0000% |
  | `price` | `float64` | 0.0000% |
  | `freight_value` | `float64` | 0.0000% |
- Date coverage:
  - shipping_limit_date: 2016-09-19 00:15:34 to 2020-04-09 22:35:08 (112,650 parseable values)
- ID uniqueness:
  - order_id: 98,666/112,650 non-null values unique
  - order_item_id: 21/112,650 non-null values unique
  - product_id: 32,951/112,650 non-null values unique
  - seller_id: 3,095/112,650 non-null values unique
- Candidate label columns (name-based; not validated targets): none detected

### olist_order_payments_dataset.csv

- Rows: 103,886
- Duplicate rows: 0
- Columns:
  | Column | Dtype | Missing % |
  |---|---|---:|
  | `order_id` | `str` | 0.0000% |
  | `payment_sequential` | `int64` | 0.0000% |
  | `payment_type` | `str` | 0.0000% |
  | `payment_installments` | `int64` | 0.0000% |
  | `payment_value` | `float64` | 0.0000% |
- Date coverage:
  - No date-like columns with parseable values detected.
- ID uniqueness:
  - order_id: 99,440/103,886 non-null values unique
- Candidate label columns (name-based; not validated targets): none detected

### olist_order_reviews_dataset.csv

- Rows: 99,224
- Duplicate rows: 0
- Columns:
  | Column | Dtype | Missing % |
  |---|---|---:|
  | `review_id` | `str` | 0.0000% |
  | `order_id` | `str` | 0.0000% |
  | `review_score` | `int64` | 0.0000% |
  | `review_comment_title` | `str` | 88.3415% |
  | `review_comment_message` | `str` | 58.7025% |
  | `review_creation_date` | `str` | 0.0000% |
  | `review_answer_timestamp` | `str` | 0.0000% |
- Date coverage:
  - review_creation_date: 2016-10-02 00:00:00 to 2018-08-31 00:00:00 (99,224 parseable values)
  - review_answer_timestamp: 2016-10-07 18:32:28 to 2018-10-29 12:27:35 (99,224 parseable values)
- ID uniqueness:
  - review_id: 98,410/99,224 non-null values unique
  - order_id: 98,673/99,224 non-null values unique
- Candidate label columns (name-based; not validated targets): `review_score`

### olist_orders_dataset.csv

- Rows: 99,441
- Duplicate rows: 0
- Columns:
  | Column | Dtype | Missing % |
  |---|---|---:|
  | `order_id` | `str` | 0.0000% |
  | `customer_id` | `str` | 0.0000% |
  | `order_status` | `str` | 0.0000% |
  | `order_purchase_timestamp` | `str` | 0.0000% |
  | `order_approved_at` | `str` | 0.1609% |
  | `order_delivered_carrier_date` | `str` | 1.7930% |
  | `order_delivered_customer_date` | `str` | 2.9817% |
  | `order_estimated_delivery_date` | `str` | 0.0000% |
- Date coverage:
  - order_purchase_timestamp: 2016-09-04 21:15:19 to 2018-10-17 17:30:18 (99,441 parseable values)
  - order_delivered_carrier_date: 2016-10-08 10:34:01 to 2018-09-11 19:48:28 (97,658 parseable values)
  - order_delivered_customer_date: 2016-10-11 13:46:32 to 2018-10-17 13:22:46 (96,476 parseable values)
  - order_estimated_delivery_date: 2016-09-30 00:00:00 to 2018-11-12 00:00:00 (99,441 parseable values)
- ID uniqueness:
  - order_id: 99,441/99,441 non-null values unique
  - customer_id: 99,441/99,441 non-null values unique
- Candidate label columns (name-based; not validated targets): none detected

### olist_products_dataset.csv

- Rows: 32,951
- Duplicate rows: 0
- Columns:
  | Column | Dtype | Missing % |
  |---|---|---:|
  | `product_id` | `str` | 0.0000% |
  | `product_category_name` | `str` | 1.8512% |
  | `product_name_lenght` | `float64` | 1.8512% |
  | `product_description_lenght` | `float64` | 1.8512% |
  | `product_photos_qty` | `float64` | 1.8512% |
  | `product_weight_g` | `float64` | 0.0061% |
  | `product_length_cm` | `float64` | 0.0061% |
  | `product_height_cm` | `float64` | 0.0061% |
  | `product_width_cm` | `float64` | 0.0061% |
- Date coverage:
  - No date-like columns with parseable values detected.
- ID uniqueness:
  - product_id: 32,951/32,951 non-null values unique
  - product_width_cm: 95/32,949 non-null values unique
- Candidate label columns (name-based; not validated targets): none detected

### olist_sellers_dataset.csv

- Rows: 3,095
- Duplicate rows: 0
- Columns:
  | Column | Dtype | Missing % |
  |---|---|---:|
  | `seller_id` | `str` | 0.0000% |
  | `seller_zip_code_prefix` | `int64` | 0.0000% |
  | `seller_city` | `str` | 0.0000% |
  | `seller_state` | `str` | 0.0000% |
- Date coverage:
  - No date-like columns with parseable values detected.
- ID uniqueness:
  - seller_id: 3,095/3,095 non-null values unique
  - seller_zip_code_prefix: 2,246/3,095 non-null values unique
- Candidate label columns (name-based; not validated targets): none detected

### product_category_name_translation.csv

- Rows: 71
- Duplicate rows: 0
- Columns:
  | Column | Dtype | Missing % |
  |---|---|---:|
  | `product_category_name` | `str` | 0.0000% |
  | `product_category_name_english` | `str` | 0.0000% |
- Date coverage:
  - No date-like columns with parseable values detected.
- ID uniqueness:
  - No ID-like columns detected by name.
- Candidate label columns (name-based; not validated targets): none detected

## Suspected leakage / limitations

- Delivery timestamps and review fields may occur after purchase; exclude them from any prediction made before those events.

This report describes observed archive contents only. Candidate labels and limitations require domain and prediction-time review.
