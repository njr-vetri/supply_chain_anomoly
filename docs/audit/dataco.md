# Dataset audit: dataco

Archive: `archive (2).zip`

## Archive files

- DataCoSupplyChainDataset.csv (95,910,149 bytes uncompressed)
- DescriptionDataCoSupplyChain.csv (3,444 bytes uncompressed)
- tokenized_access_logs.csv (95,446,364 bytes uncompressed)
- LIMITATIONS: The archive contains a field named as a late/delay outcome (verify its definition and prediction-time availability before using it as a target or feature).
- LIMITATIONS: Potential target leakage cannot be determined from column names alone; inspect event timing and label construction before modeling.

## Tables and sheets

### DataCoSupplyChainDataset.csv

- Rows: 180,519
- Duplicate rows: 0
- Columns:
  | Column | Dtype | Missing % |
  |---|---|---:|
  | `Type` | `str` | 0.0000% |
  | `Days for shipping (real)` | `int64` | 0.0000% |
  | `Days for shipment (scheduled)` | `int64` | 0.0000% |
  | `Benefit per order` | `float64` | 0.0000% |
  | `Sales per customer` | `float64` | 0.0000% |
  | `Delivery Status` | `str` | 0.0000% |
  | `Late_delivery_risk` | `int64` | 0.0000% |
  | `Category Id` | `int64` | 0.0000% |
  | `Category Name` | `str` | 0.0000% |
  | `Customer City` | `str` | 0.0000% |
  | `Customer Country` | `str` | 0.0000% |
  | `Customer Email` | `str` | 0.0000% |
  | `Customer Fname` | `str` | 0.0000% |
  | `Customer Id` | `int64` | 0.0000% |
  | `Customer Lname` | `str` | 0.0044% |
  | `Customer Password` | `str` | 0.0000% |
  | `Customer Segment` | `str` | 0.0000% |
  | `Customer State` | `str` | 0.0000% |
  | `Customer Street` | `str` | 0.0000% |
  | `Customer Zipcode` | `float64` | 0.0017% |
  | `Department Id` | `int64` | 0.0000% |
  | `Department Name` | `str` | 0.0000% |
  | `Latitude` | `float64` | 0.0000% |
  | `Longitude` | `float64` | 0.0000% |
  | `Market` | `str` | 0.0000% |
  | `Order City` | `str` | 0.0000% |
  | `Order Country` | `str` | 0.0000% |
  | `Order Customer Id` | `int64` | 0.0000% |
  | `order date (DateOrders)` | `str` | 0.0000% |
  | `Order Id` | `int64` | 0.0000% |
  | `Order Item Cardprod Id` | `int64` | 0.0000% |
  | `Order Item Discount` | `float64` | 0.0000% |
  | `Order Item Discount Rate` | `float64` | 0.0000% |
  | `Order Item Id` | `int64` | 0.0000% |
  | `Order Item Product Price` | `float64` | 0.0000% |
  | `Order Item Profit Ratio` | `float64` | 0.0000% |
  | `Order Item Quantity` | `int64` | 0.0000% |
  | `Sales` | `float64` | 0.0000% |
  | `Order Item Total` | `float64` | 0.0000% |
  | `Order Profit Per Order` | `float64` | 0.0000% |
  | `Order Region` | `str` | 0.0000% |
  | `Order State` | `str` | 0.0000% |
  | `Order Status` | `str` | 0.0000% |
  | `Order Zipcode` | `float64` | 86.2397% |
  | `Product Card Id` | `int64` | 0.0000% |
  | `Product Category Id` | `int64` | 0.0000% |
  | `Product Description` | `float64` | 100.0000% |
  | `Product Image` | `str` | 0.0000% |
  | `Product Name` | `str` | 0.0000% |
  | `Product Price` | `float64` | 0.0000% |
  | `Product Status` | `int64` | 0.0000% |
  | `shipping date (DateOrders)` | `str` | 0.0000% |
  | `Shipping Mode` | `str` | 0.0000% |
- Date coverage:
  - Days for shipping (real): 1970-01-01 00:00:00 to 1970-01-01 00:00:00.000000006 (180,519 parseable values)
  - order date (DateOrders): 2015-01-01 00:00:00 to 2018-01-31 23:38:00 (180,519 parseable values)
  - shipping date (DateOrders): 2015-01-03 00:00:00 to 2018-02-06 22:14:00 (180,519 parseable values)
- ID uniqueness:
  - Category Id: 51/180,519 non-null values unique
  - Customer Id: 20,652/180,519 non-null values unique
  - Customer Zipcode: 995/180,516 non-null values unique
  - Department Id: 11/180,519 non-null values unique
  - Order Customer Id: 20,652/180,519 non-null values unique
  - Order Id: 65,752/180,519 non-null values unique
  - Order Item Cardprod Id: 118/180,519 non-null values unique
  - Order Item Id: 180,519/180,519 non-null values unique
  - Order Zipcode: 609/24,840 non-null values unique
  - Product Card Id: 118/180,519 non-null values unique
  - Product Category Id: 51/180,519 non-null values unique
- Candidate label columns (name-based; not validated targets): `Late_delivery_risk`

### DescriptionDataCoSupplyChain.csv

- Rows: 52
- Duplicate rows: 0
- Columns:
  | Column | Dtype | Missing % |
  |---|---|---:|
  | `FIELDS` | `str` | 0.0000% |
  | `DESCRIPTION` | `str` | 0.0000% |
- Date coverage:
  - No date-like columns with parseable values detected.
- ID uniqueness:
  - No ID-like columns detected by name.
- Candidate label columns (name-based; not validated targets): none detected

### tokenized_access_logs.csv

- Rows: 469,977
- Duplicate rows: 3,249
- Columns:
  | Column | Dtype | Missing % |
  |---|---|---:|
  | `Product` | `str` | 0.0000% |
  | `Category` | `str` | 0.0000% |
  | `Date` | `str` | 0.0000% |
  | `Month` | `str` | 0.0000% |
  | `Hour` | `int64` | 0.0000% |
  | `Department` | `str` | 0.0000% |
  | `ip` | `str` | 0.0000% |
  | `url` | `str` | 0.0000% |
- Date coverage:
  - Date: 2017-09-01 06:00:00 to 2018-01-31 23:58:00 (469,977 parseable values)
- ID uniqueness:
  - No ID-like columns detected by name.
- Candidate label columns (name-based; not validated targets): none detected

## Suspected leakage / limitations

- The archive contains a field named as a late/delay outcome (verify its definition and prediction-time availability before using it as a target or feature).
- Potential target leakage cannot be determined from column names alone; inspect event timing and label construction before modeling.

This report describes observed archive contents only. Candidate labels and limitations require domain and prediction-time review.
