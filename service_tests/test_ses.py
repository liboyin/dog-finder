"""Offline SES contracts, single-attempt HTTP behaviour, and private-data boundaries."""

import io
import uuid
from email import policy
from email.parser import BytesParser
from unittest.mock import patch

import boto3
import pytest
from botocore.awsrequest import AWSResponse
from botocore.exceptions import EndpointConnectionError, ReadTimeoutError
from botocore.parsers import ResponseParserError
from botocore.stub import Stubber
from django.core.mail import EmailMultiAlternatives
from urllib3.response import HTTPResponse

import dog_finder.delivery.ses as testee

INTENT_ID = uuid.UUID("00000000-0000-0000-0000-000000000001")


@pytest.fixture
def session(tmp_path, monkeypatch):
    """Use synthetic credentials and test-owned config, never host profiles or metadata."""
    monkeypatch.setenv("AWS_CONFIG_FILE", str(tmp_path / "config"))
    monkeypatch.setenv("AWS_SHARED_CREDENTIALS_FILE", str(tmp_path / "credentials"))
    monkeypatch.setenv("AWS_EC2_METADATA_DISABLED", "true")
    monkeypatch.delenv("AWS_PROFILE", raising=False)
    monkeypatch.delenv("AWS_DEFAULT_PROFILE", raising=False)
    return boto3.Session(aws_access_key_id="testing", aws_secret_access_key="testing")


@pytest.fixture
def sender(session):
    """Own and close one sender, with sockets prohibited by the pytest configuration."""
    adapter = testee.SesSender("ap-southeast-2", "test-events", session=session)
    try:
        yield adapter
    finally:
        adapter.close()


@pytest.fixture
def message():
    """Create synthetic multipart content including a non-credential unsubscribe URL."""
    email = EmailMultiAlternatives(
        "A dog for José",
        "Plain-text dog details",
        "Dog Finder <alerts@example.org>",
        ["recipient@example.org"],
        headers={
            "List-Unsubscribe": "<https://example.org/s/unsubscribe/synthetic/>",
            "List-Unsubscribe-Post": "List-Unsubscribe=One-Click",
        },
    )
    email.attach_alternative("<p>Dog details for José</p>", "text/html")
    return email


def test_request_preserves_mime_headers_and_has_only_id_tags(sender, message):
    """SES receives one recipient, intact MIME and explicit tracking disablement."""
    response = {"MessageId": "provider-id", "ResponseMetadata": {"HTTPStatusCode": 200}}
    with patch.object(sender._client, "send_email", return_value=response) as send:
        result = sender.send(INTENT_ID, message)
    assert result == testee.SendResult("accepted", message_id="provider-id")
    request = send.call_args.kwargs
    assert request["FromEmailAddress"] == message.from_email
    assert request["Destination"] == {"ToAddresses": message.to}
    assert request["EmailTags"] == [{"Name": "intent_id", "Value": str(INTENT_ID)}]
    assert request["ConfigurationSetName"] == "test-events"
    assert request["ConfigurationOverrides"] == {
        "Tracking": {"OpenTrackingEnabled": "DISABLED", "ClickTrackingEnabled": "DISABLED"}
    }
    raw = request["Content"]["Raw"]["Data"]
    rendered = BytesParser(policy=policy.default).parsebytes(raw)
    assert rendered["Subject"] == message.subject
    assert str(rendered["To"]) == message.to[0]
    assert rendered["List-Unsubscribe"] == message.extra_headers["List-Unsubscribe"]
    assert rendered["List-Unsubscribe-Post"] == "List-Unsubscribe=One-Click"
    assert rendered.get_body("plain").get_content().strip() == message.body
    assert rendered.get_body("html").get_content().strip() == message.alternatives[0].content
    assert b"\r\n" in raw
    # Check the request against the installed SDK model, not only our mock's expectations.
    with Stubber(sender._client) as stub:
        stub.add_response("send_email", response)
        assert sender.send(INTENT_ID, message).status == "accepted"
        stub.assert_no_pending_responses()


@pytest.mark.parametrize(
    "code,status",
    [
        ("AccountSuspendedException", 400),
        ("BadRequestException", 400),
        ("LimitExceededException", 400),
        ("MailFromDomainNotVerifiedException", 400),
        ("MessageRejected", 400),
        ("NotFoundException", 404),
        ("SendingPausedException", 400),
        ("TooManyRequestsException", 429),
    ],
)
def test_documented_rejection_is_not_acceptance(sender, message, code, status, caplog):
    """Known SES rejection codes with their expected HTTP status are safely classified."""
    with Stubber(sender._client) as stub:
        stub.add_client_error(
            "send_email",
            service_error_code=code,
            service_message="private provider text",
            http_status_code=status,
        )
        result = sender.send(INTENT_ID, message)
        stub.assert_no_pending_responses()
    assert result == testee.SendResult("rejected", reason=code)
    assert "private provider text" not in repr(result) + caplog.text


@pytest.mark.parametrize(
    "code,status",
    [("InternalServerError", 500), ("NewUnknownError", 400), ("MessageRejected", 500)],
)
def test_unexpected_error_is_ambiguous_not_retryable(sender, message, code, status):
    """Unrecognized failures and inconsistent HTTP statuses cannot authorize another send."""
    with Stubber(sender._client) as stub:
        stub.add_client_error("send_email", service_error_code=code, http_status_code=status)
        assert sender.send(INTENT_ID, message) == testee.SendResult(
            "acceptance_unknown", reason="unexpected_provider_error"
        )


@pytest.mark.parametrize("message_id", [None, "", 123, "private@example.org", "x" * 257])
def test_malformed_success_is_ambiguous(sender, message, message_id):
    """A success without a valid provider ID cannot be recorded as accepted or retried."""
    response = {"MessageId": message_id, "ResponseMetadata": {"HTTPStatusCode": 200}}
    with patch.object(sender._client, "send_email", return_value=response):
        assert sender.send(INTENT_ID, message) == testee.SendResult(
            "acceptance_unknown", reason="invalid_provider_response"
        )


def test_unexpected_success_status_is_ambiguous(sender, message):
    """An ID alone is not sufficient without the documented successful HTTP response."""
    with patch.object(sender._client, "send_email", return_value={"MessageId": "provider-id"}):
        assert sender.send(INTENT_ID, message).status == "acceptance_unknown"


def test_sdk_parser_failure_is_ambiguous_without_exposing_body(sender, message, caplog):
    """An unparseable response may follow acceptance and must not leak response content."""
    error = ResponseParserError("private response body")
    with patch.object(sender._client, "send_email", side_effect=error) as send:
        result = sender.send(INTENT_ID, message)
    assert result == testee.SendResult("acceptance_unknown", reason="transport_error")
    assert send.call_count == 1
    assert "private response body" not in repr(result) + caplog.text


@pytest.mark.parametrize("failure", ["http", "timeout", "connection"])
def test_sdk_does_not_retry_an_ambiguous_http_attempt(sender, message, failure):
    """Exercise botocore's actual retry handler while replacing only its HTTP transport."""
    if failure == "http":
        raw = HTTPResponse(body=io.BytesIO(b'{"message":"unavailable"}'), preload_content=False)
        outcome = {"return_value": AWSResponse("https://example.org", 503, {}, raw)}
    else:
        error = ReadTimeoutError if failure == "timeout" else EndpointConnectionError
        outcome = {"side_effect": error(endpoint_url="https://example.org")}
    with patch.object(sender._client._endpoint.http_session, "send", **outcome) as send:
        result = sender.send(INTENT_ID, message)
    assert result.status == "acceptance_unknown"
    assert send.call_count == 1


def test_explicit_config_overrides_environment_retries_and_endpoint(session, monkeypatch):
    """Host retry/endpoint settings cannot quietly turn one intended send into several."""
    monkeypatch.setenv("AWS_MAX_ATTEMPTS", "10")
    monkeypatch.setenv("AWS_ENDPOINT_URL", "http://untrusted.example.org")
    with patch.object(testee.boto3, "Session", return_value=session):
        adapter = testee.SesSender("ap-southeast-2", "test-events")
    try:
        config = adapter._client.meta.config
        assert config.retries == {"mode": "standard", "total_max_attempts": 1}
        assert (config.connect_timeout, config.read_timeout, config.max_pool_connections) == (
            5,
            30,
            1,
        )
        assert adapter._client.meta.endpoint_url == "https://email.ap-southeast-2.amazonaws.com"
    finally:
        adapter.close()


@pytest.mark.parametrize("region,config", [(" ", "events"), ("au", ""), ("au", "bad value")])
def test_invalid_configuration_fails_before_client_creation(region, config):
    """An explicit region and valid event configuration set are required without echoing them."""
    with patch.object(testee.boto3, "Session") as session:
        with pytest.raises(ValueError, match="requires a region"):
            testee.SesSender(region, config)
    session.assert_not_called()


@pytest.mark.parametrize(
    "field,value",
    [
        ("to", []),
        ("to", [""]),
        ("to", ["a", "b"]),
        ("cc", ["a"]),
        ("bcc", ["a"]),
        ("from_email", ""),
    ],
)
def test_invalid_envelope_never_calls_ses(sender, message, field, value):
    """Messages cannot accidentally send to a second recipient or omit their sender."""
    setattr(message, field, value)
    with patch.object(sender._client, "send_email") as send:
        with pytest.raises(ValueError, match="exactly one recipient"):
            sender.send(INTENT_ID, message)
    send.assert_not_called()


def test_non_id_correlation_tag_never_calls_ses(sender, message):
    """A mistaken address or description cannot enter provider correlation tags."""
    with patch.object(sender._client, "send_email") as send:
        with pytest.raises(ValueError, match="intent UUID"):
            sender.send("private@example.org", message)
    send.assert_not_called()


def test_header_injection_is_sanitized_before_sending(sender, message):
    """Invalid headers cause a local, non-sensitive error without any provider attempt."""
    message.subject = "private value\r\nBcc: hidden@example.org"
    with patch.object(sender._client, "send_email") as send:
        with pytest.raises(ValueError, match="^Email could not be serialized safely$"):
            sender.send(INTENT_ID, message)
    send.assert_not_called()


def test_oversized_email_is_not_truncated_or_sent(sender, message):
    """The message bound fails explicitly instead of dropping eligible content."""
    message.body = "x" * (testee.MAX_MESSAGE_BYTES + 1)
    with patch.object(sender._client, "send_email") as send:
        with pytest.raises(ValueError, match="size limit"):
            sender.send(INTENT_ID, message)
    send.assert_not_called()
