# Dog Finder

Daily adoption alerts for Australian rescue dogs. The SaaS is being built: the current
application provides a local search creation/confirmation/editing/cancellation preview, health
probes, and a tested development scaffold. Public registration is closed; matching and
live email delivery are not implemented yet.

Product behaviour lives in [USER_STORIES.md](USER_STORIES.md), architecture and budget
in [DESIGN.md](DESIGN.md), and implementation work in [TODO.md](TODO.md).

## Python environment

Install [uv](https://docs.astral.sh/uv/getting-started/installation/), then:

```sh
uv sync --locked
uv run python --version
```

The project pins Python 3.12 in `.python-version`. uv downloads a compatible interpreter
if needed and creates `.venv/`; `uv.lock` records exact dependencies. Activation is
optional because `uv run` selects the environment. The system Python is not changed.

## Development

Start a local PostgreSQL 16 database with Docker Compose, if Docker is available:

```sh
docker compose up -d --wait db
uv run python manage.py migrate
uv run python manage.py runserver 127.0.0.1:8000
```

Alternatively supply a locally installed PostgreSQL database. Development defaults use
`dog_finder_dev` on `127.0.0.1:55432`, with the local-only credentials in `compose.yaml`.
Override `DATABASE_NAME`, `DATABASE_USER`, `DATABASE_PASSWORD`, `DATABASE_HOST`, and
`DATABASE_PORT` when needed. Copy `.env.example` to an ignored `.env` and explicitly load
it with `uv run --env-file .env python manage.py runserver`; settings do not read secret
files automatically. Do not reuse development credentials in production.

The landing page and `/health/` work without PostgreSQL. `/ready/` checks PostgreSQL and
returns HTTP 503 if it is unavailable. These probes only report application/database
availability, not the health of the future daily processing pipeline.

Local email uses Django's in-memory backend. No source fetches, AI calls, email sends,
or background jobs start automatically. Procrastinate and provider adapters will be
added with their first working features.

## Subscriber preview

After applying migrations, load a postcode reference from an operator-downloaded
[GeoNames Australian postal archive](https://download.geonames.org/export/zip/AU.zip):

```sh
uv run python manage.py load_postcodes /path/to/AU.zip
```

The command reads only the local archive and validates it before atomically replacing
the postcode/state table. No test downloads this reference. The GeoNames dataset is
attributed in the preview pages under CC BY 4.0; its source README notes that accuracy
and completeness are not guaranteed. Postcodes spanning states require an explicit
choice. See [GeoNames data information](https://download.geonames.org/export/zip/).

The archive checked on 2026-09-21 yielded 3,188 distinct postcode/state pairs (SHA-256
`8318f2627f3fb6d22cf5ce89ba8fcb6c7b7b872220fc4647dcac890eff66db81`). This is
provenance for that import, not a claim that future downloads are identical. Only
postcode/state pairs are currently imported; distance centroids remain future work.

Visit `/search/new/` in development. The form validates email, postcode/state, explicit
interstate choice, name, and a trimmed description of at most 300 characters. Confirmation
emails are captured in the Django process's in-memory outbox, exercised end to end by
pytest; they do not arrive in a real inbox, and there is no public mailbox preview route.
The completed SES workflow is needed for normal browser-to-inbox use. Do not log or
publish captured private links to work around this boundary.

Confirmation requires a CSRF-protected button press, is valid for seven days, and is
consumed only on successful activation. Activation starts a 90-day term and leaves source
baselining pending. An unguessable management link shows one search and supports explicit
cancellation. GET requests do not activate or cancel; cancellation removes stored criteria.

The private edit page updates active, unexpired, unsuppressed searches using the same
validation as creation, without changing the email address or expiry. A matching-criteria
change increments the criteria revision and marks the baseline pending; a rename preserves
both. Stale forms are rejected instead of overwriting another tab's changes. Reload the
form to reconcile them. Credentials and lifecycle state are rechecked under the same
transaction lock used by cancellation, so an edit cannot restore cancelled criteria.
There are no candidate queues or sent-listing records yet; integrating their edit/reset
and preservation rules remains part of the matching milestone.

The management page offers **Keep searching** for active searches and for 30 days after
expiry. Its confirmation button requires a CSRF-protected POST; GETs never renew. Renewal
sets expiry to the later of the current expiry and 90 days from the request, so repeated
clicks do not accumulate extra terms. Renewal before expiry preserves the baseline.
Grace-period renewal reacquires both search and subscriber capacity, advances the matching
revision, marks the baseline pending, and invalidates old edit forms. It keeps the same
search identity and criteria. The exact 30-day deadline is excluded, consistently with
housekeeping. Cancelled, suppressed, and unconfirmed searches cannot renew. Expiry is
evaluated at request time, so no timer is needed to release capacity or stop eligibility.
Reminder emails and integration with future candidate/sent-listing records are not yet
implemented.

**Find my alerts** at `/search/recover/` captures a recovery email locally for addresses
with active searches or expired searches still inside the 30-day grace period. Public
receipts are identical for unknown, suppressed, and limited addresses. Recovery shares
the three-emails-per-UTC-day address counter and source-request counter with confirmation;
it does not create subscribers or consume additional capacity. Its request form is disabled
alongside registration in production, and its service rejects live email backends.

Recovery links use a seven-day window and require a CSRF-protected button press before
being consumed. A successful use invalidates all outstanding recovery links for that
address without changing searches. By default, existing management links remain valid.
An optional, unchecked **Replace all my management links** checkbox revokes the address-wide
credential and every individual search's management credential in the same transaction.
Only the mailbox recovery link can authorize replacement, not an existing dashboard link.
The resulting dashboard provides fresh links; old browser edit/cancel/renew operations
recheck credentials under the lifecycle lock. A mutation that obtained that lock before
replacement can finish first; replacement does not undo it or erase previously opened
pages. Search criteria, baselines, expiry, confirmation links, and native one-click
unsubscribe credentials are preserved. Save the new dashboard URL after replacement.
It opens a separately
scoped, masked-email dashboard listing active searches and grace-period renewal options,
with links to existing edit, cancel, and renewal pages. Pending, cancelled, fully expired,
and other addresses' searches are excluded. The recovery email also lists grace-period
searches with their individual renewal links. A single-search or unsubscribe credential
cannot open the address-wide dashboard.

Transactions enforce five active searches per address and 250 distinct active subscribers.
Additional searches for existing subscribers do not need another subscriber slot. Expired
searches do not occupy a slot. UTC-day counters permit three confirmation emails per
address and, initially, 20 valid requests per source IP. The IP is stored only as a keyed
hash. At most 750 pending searches are retained. Proxies must supply a trustworthy peer
address before public launch; the preview uses `REMOTE_ADDR`, not forwarded headers.
Suppression and quota outcomes share the same public receipt.

Run housekeeping daily once the lifecycle is operated outside tests:

```sh
uv run python manage.py purge_searches
```

It deletes abandoned seven-day confirmations, cancelled searches, and expired searches
beyond the 30-day grace period, without touching other searches at the same address.
Same-day email counters and suppressed addresses are retained. A production scheduler
and minimal durable suppression records are part of subsequent work; no timer is installed
by this feature. Reminders and durable provider delivery
also remain outstanding before launch.

The native unsubscribe receiver at `/s/unsubscribe/<token>/` accepts the
[RFC 8058](https://www.rfc-editor.org/rfc/rfc8058) form POST
`List-Unsubscribe=One-Click` (URL-encoded or multipart). Its separately signed,
revocable credential can only cancel one search; it cannot reveal criteria or grant
management access. This endpoint alone is CSRF-exempt and does not depend on cookies.
GET/HEAD and other methods return 405 without changes; malformed payloads return 400.
Valid-shaped POSTs return an empty 204 without redirects, including invalid, revoked,
already-cancelled, and deleted links. Retries preserve the original cancellation time.
Cancellation uses the shared lifecycle lock, removes criteria, and does not cancel sibling
searches or suppress the whole address. HTTPS, outgoing List-Unsubscribe headers, DKIM
coverage of both unsubscribe headers, and queued-send rechecks remain requirements for
the future SES integration. No real email client integration is enabled by this receiver.

Private pages send `no-store` and `no-referrer`. Django logs redact private `/s/` requests.
Any future reverse proxy or access/error logging service must likewise omit or redact
these paths and must not capture form bodies. Production settings disable registration;
the current creation service also rejects any email backend other than local capture.

## Tests and checks

All tests run through pytest. New service tests use pytest functions; retained parser
tests are still collected by pytest without requiring a wholesale rewrite.

Without PostgreSQL:

```sh
uv run pytest -m 'not database'
uv run ruff check .
uv run ruff format --check .
uv run python manage.py check
```

Full tests use a separate disposable database server:

```sh
docker compose --profile test up -d --wait test-db
uv run pytest --allow-hosts=127.0.0.1 --cov --cov-report=term-missing
uv run python manage.py check --settings=dog_finder.settings.test
uv run python manage.py makemigrations --check --dry-run --settings=dog_finder.settings.test
docker compose --profile test stop test-db
```

Test settings use only `TEST_DATABASE_*` connection variables, the control database
`dog_finder_test_control`, and pytest-django's disposable `test_dog_finder` database.
The test role needs permission to create databases. Never supply production credentials.
For a native test server, set `TEST_DATABASE_HOST`, `TEST_DATABASE_PORT`,
`TEST_DATABASE_USER`, and `TEST_DATABASE_PASSWORD`. A Unix socket directory can be used
as the host instead of TCP. The Compose test server stores its data in temporary memory;
the development server uses a persistent named volume. Do not remove that volume to
clean up a test run.

Network sockets are blocked in tests by default; Unix sockets are allowed. The full
TCP test command permits only loopback access for the test database. Database access
also requires pytest-django's explicit database marker. External APIs must use fakes.

Coverage requires 100% statement/branch coverage of the small new application logic.
Settings modules and the WSGI import entry point are excluded because they are checked
through configuration and startup smoke checks; deployment must repeat those checks
with its actual environment. Retained extraction code in `src/` has its own tests and
is outside the new service coverage and Ruff gates until migrated. No coverage claim is
made for it. CI runs the full suite using PostgreSQL 16 and the locked dependencies.
Generated subscription migrations are excluded from Python coverage; migration application,
rollback, and reapplication are verified against a disposable PostgreSQL database.

## Production boundary

`dog_finder.settings.production` requires `DJANGO_SECRET_KEY`, `ALLOWED_HOSTS`, and all
database credentials. It disables debug, requires HTTPS, and secures cookies. WSGI
defaults to production settings. Before any deployment, run Django's deployment checks
with real deployment configuration and configure the trusted reverse proxy to overwrite
`X-Forwarded-Proto`; the application must not be publicly reachable around that proxy.

```sh
uv run python manage.py check --deploy --settings=dog_finder.settings.production
uv run gunicorn dog_finder.wsgi:application --bind 127.0.0.1:8000
```

These are deployment entry points, not a deployed service. Production email remains
in-memory until the durable SES integration is implemented. No subscriber-facing launch
is implied by a passing framework check.

## Personal automation retired

The owner authorized retirement on 20 September 2026. The local
`dog-finder-daily-refresh.timer` was disabled and stopped; its service was also stopped.
The runner, systemd deployment files, personal source configuration, prompts, verdict
schema, state writer, renderer, and their obsolete tests have been removed. They remain
recoverable in Git history.

Reusable parsers, fetching, URL deduplication, and fixtures remain in `src/` and `tests/`.
They are not yet wired into the SaaS and retain legacy assumptions that must be reviewed
before reuse. Existing `data/`, ignored run artifacts, and logs are historical data;
the SaaS does not read or migrate them. Existing local changes to that data are preserved.
