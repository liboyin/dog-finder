"""Single-attempt SES transport, to be called only by a durable delivery workflow."""

import re
import uuid
from dataclasses import dataclass
from typing import Literal

import boto3
from botocore.config import Config
from botocore.exceptions import BotoCoreError, ClientError
from botocore.parsers import ResponseParserError
from django.core.mail import EmailMessage

MAX_MESSAGE_BYTES = 1024 * 1024
# Only documented SendEmail rejections are definite; unexpected responses fail closed.
REJECTIONS = {
    "AccountSuspendedException": 400,
    "BadRequestException": 400,
    "LimitExceededException": 400,
    "MailFromDomainNotVerifiedException": 400,
    "MessageRejected": 400,
    "NotFoundException": 404,
    "SendingPausedException": 400,
    "TooManyRequestsException": 429,
}


@dataclass(frozen=True)
class SendResult:
    """Privacy-safe transport outcome, never evidence of inbox delivery.

    Unknown outcomes must be reconciled, not retried. Rejection permits the durable
    workflow to decide on a later attempt; this transport never schedules one.
    """

    status: Literal["accepted", "rejected", "acceptance_unknown"]
    message_id: str = ""
    reason: str = ""


class SesSender:
    """Own a bounded SES client with no SDK retries or implicit application wiring.

    Construction is explicit and may resolve deployment credentials. Call close()
    when finished. Before calling send(), the future orchestrator must persist its
    intent/attempt, check lifecycle and budgets, and own ambiguity reconciliation.
    Do not use this as a Django email backend or a retryable preview task.
    """

    def __init__(
        self, region: str, configuration_set: str, *, session: boto3.Session | None = None
    ) -> None:
        """Create a regional client; require event routing and ignore endpoint overrides."""
        if not region.strip() or not re.fullmatch(r"[A-Za-z0-9_-]{1,64}", configuration_set):
            raise ValueError("SES requires a region and an event configuration set")
        self.configuration_set = configuration_set
        self._client = (session or boto3.Session()).client(
            "sesv2",
            region_name=region,
            config=Config(
                retries={"mode": "standard", "total_max_attempts": 1},
                connect_timeout=5,
                read_timeout=30,
                max_pool_connections=1,
                ignore_configured_endpoint_urls=True,
            ),
        )

    def close(self) -> None:
        """Release the client's HTTP connection pool without sending anything."""
        self._client.close()

    def send(self, intent_id: uuid.UUID, message: EmailMessage) -> SendResult:
        """Attempt one bounded single-recipient MIME send and sanitize provider failures.

        Invalid local input raises ValueError before any send. Once invoked, transport
        failures and malformed success responses are ambiguous, including crashes the
        caller must recover from its persisted attempt. Nothing here retries or logs
        message contents, SDK exceptions, or provider error text.
        """
        if (
            not isinstance(intent_id, uuid.UUID)
            or len(message.to) != 1
            or not message.to[0]
            or message.cc
            or message.bcc
            or not message.from_email
        ):
            raise ValueError("SES requires an intent UUID, sender, and exactly one recipient")
        try:
            raw = message.message().as_bytes(linesep="\r\n")
        except ValueError:
            raise ValueError("Email could not be serialized safely") from None
        if len(raw) > MAX_MESSAGE_BYTES:
            raise ValueError("Email exceeds the application's size limit")
        try:
            response = self._client.send_email(
                FromEmailAddress=message.from_email,
                Destination={"ToAddresses": message.to},
                Content={"Raw": {"Data": raw}},
                ConfigurationSetName=self.configuration_set,
                EmailTags=[{"Name": "intent_id", "Value": str(intent_id)}],
                ConfigurationOverrides={
                    "Tracking": {
                        "OpenTrackingEnabled": "DISABLED",
                        "ClickTrackingEnabled": "DISABLED",
                    }
                },
            )
        except ClientError as exc:
            code = exc.response.get("Error", {}).get("Code", "")
            status = exc.response.get("ResponseMetadata", {}).get("HTTPStatusCode")
            if code in REJECTIONS and status == REJECTIONS[code]:
                return SendResult("rejected", reason=code)
            return SendResult("acceptance_unknown", reason="unexpected_provider_error")
        except (BotoCoreError, ResponseParserError):
            return SendResult("acceptance_unknown", reason="transport_error")
        message_id = response.get("MessageId")
        if (
            response.get("ResponseMetadata", {}).get("HTTPStatusCode") != 200
            or not isinstance(message_id, str)
            or not re.fullmatch(r"[A-Za-z0-9_-]{1,256}", message_id)
        ):
            return SendResult("acceptance_unknown", reason="invalid_provider_response")
        return SendResult("accepted", message_id=message_id)
