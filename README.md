# Dog Finder

Daily adoption alerts for Australian rescue dogs. The SaaS is being built: the current
application provides a landing page, health probes, and a tested development scaffold.
Registration, matching jobs, and email delivery are not implemented yet.

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
