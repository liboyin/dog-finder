# Known issues

Open issues found in code review, ordered by impact. Each lists the affected
location, the impact, and a suggested fix. Resolved issues should be removed,
not struck through — git history is the record.

## 4. Redundant raw-URL clause in `flag_disappeared`

- **Where:** the membership check in `flag_disappeared`, [src/store.py](src/store.py).
- **Impact:** `present` only ever contains canonical keys, so `entry["url"] not in present` is effectively always true and contributes nothing; only `canonical(entry["url"]) not in present` does real work. Harmless but misleading to a future reader.
- **Suggested fix:** Drop the raw-URL clause and keep the canonical check.
