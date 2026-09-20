"""Avoid recording private capability paths in Django request logs."""

import logging


class PrivateRequests(logging.Filter):
    """Redact private-route request messages, including attached exception details."""

    def filter(self, record: logging.LogRecord) -> bool:
        """Retain operational status without token-bearing paths or request objects."""
        request = getattr(record, "request", None)
        if "/s/" in record.getMessage() or (request and request.path.startswith("/s/")):
            record.msg = "Private search request (details withheld)"
            record.args = ()
            record.exc_info = record.exc_text = record.stack_info = None
            record.request = None
        return True
