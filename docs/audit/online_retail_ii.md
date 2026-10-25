# Dataset audit: online_retail_ii

Archive: `online+retail+ii.zip`

## Archive files

- online_retail_II.xlsx (45,622,278 bytes uncompressed)
- LIMITATIONS: This is transaction/demand data; it does not establish inventory levels or stockout labels.

## Tables and sheets

### online_retail_II.xlsx [Year 2009-2010]

- Rows: 525,461
- Duplicate rows: 6,865
- Columns:
  | Column | Dtype | Missing % |
  |---|---|---:|
  | `Invoice` | `object` | 0.0000% |
  | `StockCode` | `object` | 0.0000% |
  | `Description` | `object` | 0.5572% |
  | `Quantity` | `int64` | 0.0000% |
  | `InvoiceDate` | `datetime64[us]` | 0.0000% |
  | `Price` | `float64` | 0.0000% |
  | `Customer ID` | `float64` | 20.5395% |
  | `Country` | `str` | 0.0000% |
- Date coverage:
  - Invoice: 1970-01-01 00:00:00.000489434 to 1970-01-01 00:00:00.000538171 (515,252 parseable values)
  - InvoiceDate: 2009-12-01 07:45:00 to 2010-12-09 20:01:00 (525,461 parseable values)
- ID uniqueness:
  - StockCode: 4,632/525,461 non-null values unique
  - Customer ID: 4,383/417,534 non-null values unique
- Candidate label columns (name-based; not validated targets): none detected

### online_retail_II.xlsx [Year 2010-2011]

- Rows: 541,910
- Duplicate rows: 5,268
- Columns:
  | Column | Dtype | Missing % |
  |---|---|---:|
  | `Invoice` | `object` | 0.0000% |
  | `StockCode` | `object` | 0.0000% |
  | `Description` | `object` | 0.2683% |
  | `Quantity` | `int64` | 0.0000% |
  | `InvoiceDate` | `datetime64[us]` | 0.0000% |
  | `Price` | `float64` | 0.0000% |
  | `Customer ID` | `float64` | 24.9266% |
  | `Country` | `str` | 0.0000% |
- Date coverage:
  - Invoice: 1970-01-01 00:00:00.000536365 to 1970-01-01 00:00:00.000581587 (532,619 parseable values)
  - InvoiceDate: 2010-12-01 08:26:00 to 2011-12-09 12:50:00 (541,910 parseable values)
- ID uniqueness:
  - StockCode: 4,070/541,910 non-null values unique
  - Customer ID: 4,372/406,830 non-null values unique
- Candidate label columns (name-based; not validated targets): none detected

## Suspected leakage / limitations

- This is transaction/demand data; it does not establish inventory levels or stockout labels.

This report describes observed archive contents only. Candidate labels and limitations require domain and prediction-time review.
