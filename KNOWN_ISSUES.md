# Known issues

Open issues found in code review, ordered by impact. Each lists the affected
location, the impact, and a suggested fix. Resolved issues should be removed,
not struck through — git history is the record.

## 2. `state.json` is written non-atomically

- **Where:** `save_state` in [src/store.py](src/store.py).
- **Impact:** The authoritative record is written directly to its target path. In the unattended nightly job, a crash or kill mid-`json.dump` leaves a truncated file; the next run's `load_state` then fails with `JSONDecodeError` and the whole pipeline is down until a human restores it from git.
- **Suggested fix:** Write to a temp file in the same directory and `os.replace()` it onto the target (atomic on POSIX), so an interrupted write never corrupts the existing state.

## 3. Detail-fetch failures are silently under-reported

- **Where:** the detail-fetch loop in `_collect_source`, [src/pipeline.py](src/pipeline.py).
- **Impact:** When a per-dog detail fetch/parse fails, the code sets `base.error` but (a) leaves `status = OK`, so `_result_detail` never surfaces the error in the per-shelter log line, and (b) overwrites `base.error` on each iteration, so only the last failing dog survives. A shelter whose detail pages all fail still logs as healthy `OK`, and the un-enriched cards (no breed/fee) are upserted as pending.
- **Suggested fix:** Accumulate a detail-error count (and/or keep the first error) rather than overwriting, and reflect detail failures in the logged result so a systematically broken detail parser is visible without reading the manifest JSON.

## 4. Redundant raw-URL clause in `flag_disappeared`

- **Where:** the membership check in `flag_disappeared`, [src/store.py](src/store.py).
- **Impact:** `present` only ever contains canonical keys, so `entry["url"] not in present` is effectively always true and contributes nothing; only `canonical(entry["url"]) not in present` does real work. Harmless but misleading to a future reader.
- **Suggested fix:** Drop the raw-URL clause and keep the canonical check.
