# Dataset register

The three archives were found in the workspace root. They are not moved or extracted. Their SHA-256 hashes below were calculated before the audit and must be compared with the post-audit verification.

| Dataset | Filename | Path | Compressed size (bytes) | SHA-256 | License |
|---|---|---|---:|---|---|
| Olist | `archive (1).zip` | `C:\Projects\supply-chain-risk-system\archive (1).zip` | 44,717,580 | `967E41E04FC306FE604E2A693F488995A8B41E5047418F8A5C8E4ABD6DECA784` | UNKNOWN |
| DataCo | `archive (2).zip` | `C:\Projects\supply-chain-risk-system\archive (2).zip` | 26,920,609 | `96F3A04CE2E5384248B393F20221AB9D16B33F94B9AF72439170E8E220D7B0B1` | UNKNOWN |
| UCI Online Retail II | `online+retail+ii.zip` | `C:\Projects\supply-chain-risk-system\online+retail+ii.zip` | 45,622,418 | `572E36277C2390FBFDE10664750731E0A86F55E33470D91919085F0408E67BFB` | UNKNOWN |

## Verification needed

For each dataset, locate and review the original publisher's dataset page, license/terms applicable to this exact download, attribution requirements, redistribution and derivative-work restrictions, and any research-use conditions. Record a license only after verifying that the terms cover the downloaded files; otherwise retain UNKNOWN.

## Scope notes

- Olist: orders, delivery timelines, delays, and reviews. Keep tables in this source together only where keys and semantics are verified.
- DataCo: delay classification data; target/leakage risk requires checking feature availability at the prediction timestamp and the target's construction.
- UCI Online Retail II: use for demand/forecasting only. The archive does not establish inventory or stockout labels.

See the corresponding reports in `docs/audit/` for observed archive members and per-table profiles.
