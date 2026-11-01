"""Published v4.1.1 Responses-SSE greeting contracts; no SDK/network required."""

from contextlib import redirect_stdout
import io
import json
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch

from config.deployment import hosted


def completion(text="Hello! How can I help?"):
    return {
        "type": "response.completed", "sequence_number": 7,
        "response": {
            "id": "resp-test", "object": "response", "created_at": 0.0,
            "model": "test-model", "status": "completed",
            "conversation": {"id": "conv-test"},
            "tools": [], "tool_choice": "none", "parallel_tool_calls": False,
            "output": [{
                "id": "msg-test", "type": "message", "role": "assistant",
                "status": "completed",
                "content": [{
                    "type": "output_text", "text": text,
                    "annotations": [], "logprobs": [],
                }],
            }],
        },
    }


def sse(*events):
    return "".join(f'event: {event["type"]}\ndata: {json.dumps(event)}\n\n' for event in events)


class HostedSmokeTests(unittest.TestCase):
    def test_custom_responses_json_and_raw_http(self):
        response = json.dumps(completion()["response"])
        hosted.validate_responses_smoke_output(response)
        hosted.validate_responses_smoke_output("HTTP/1.1 200 OK\r\nContent-Type: application/json\r\n\r\n" + response)
        hosted.validate_responses_smoke_output(sse(completion()))
        for body in ("HTTP/1.1 403 Forbidden\n\n" + response,
                     json.dumps(completion("")), '{"object":"response","status":"failed"}',
                     '{"object":"response","status":"completed","error":{"message":"PRIVATE-MARKER"}}'):
            with self.subTest(body=body), self.assertRaises(ValueError) as caught:
                hosted.validate_responses_smoke_output(body)
            self.assertNotIn("PRIVATE-MARKER", str(caught.exception))

    def test_custom_protocol_is_read_from_selected_service(self):
        root = Path(__file__).resolve().parents[1]
        self.assertEqual("responses", hosted.service_protocol(root / "samples/custom-app/hosted/azure.yaml", "agent"))
        with tempfile.TemporaryDirectory() as directory:
            project = Path(directory) / "azure.yaml"
            project.write_text("services:\n  agent:\n    protocols:\n      - protocol: invocations\n", encoding="utf-8")
            self.assertEqual("invocations", hosted.service_protocol(project, "agent"))
            project.write_text("services:\n  agent:\n    protocols:\n      - protocol: a2a\n", encoding="utf-8")
            with self.assertRaises(ValueError):
                hosted.service_protocol(project, "agent")

    def test_successful_completed_greeting_sse_not_exact_marker(self):
        hosted.validate_smoke_output("Invoking agent...\n" + sse(
            {"type": "response.output_text.delta", "delta": "Hello!"},
            completion(),
        ) + "Invocation complete.\n")

    def test_cli_json_events_and_transport_comments(self):
        hosted.validate_smoke_output(json.dumps(completion()) + "\n")
        hosted.validate_smoke_output(": keepalive\n" + sse(completion()) + "data: [DONE]\n\n")

    def test_word_error_in_model_text_is_not_an_error_frame(self):
        hosted.validate_smoke_output(sse(completion('Hello! The word "error" is text.')))

    def test_old_phrase_alone_or_delta_is_not_completion(self):
        for output in (
            "Agent Landing Zone hosted smoke OK.",
            sse({"type": "response.output_text.delta", "delta": "Agent Landing Zone hosted smoke OK."}),
            sse({"type": "response.output_text.done", "text": "Hello!"}),
            "data: [DONE]\n\n", "",
        ):
            with self.subTest(output=output), self.assertRaises(ValueError):
                hosted.validate_smoke_output(output)

    def test_error_before_or_after_completion_fails(self):
        for error_type in ("error", "response.failed", "response.incomplete", "response.cancelled"):
            for events in (({"type": error_type}, completion()), (completion(), {"type": error_type})):
                with self.subTest(error_type=error_type), self.assertRaises(ValueError):
                    hosted.validate_smoke_output(sse(*events))

    def test_empty_text_or_nonassistant_output_fails(self):
        for text in ("", " \r\n\t"):
            with self.subTest(text=text), self.assertRaises(ValueError):
                hosted.validate_smoke_output(sse(completion(text)))
        for key, value in (("role", "user"), ("type", "function_call"), ("status", "in_progress"), ("content", [])):
            event = completion()
            event["response"]["output"][0][key] = value
            with self.subTest(key=key), self.assertRaises(ValueError):
                hosted.validate_smoke_output(sse(event))

    def test_failed_status_nested_error_or_missing_output_fails(self):
        for key, value in (
            ("status", "in_progress"), ("status", "failed"),
            ("error", {"message": "PRIVATE-MARKER"}), ("output", None),
            ("output", []),
        ):
            event = completion()
            event["response"][key] = value
            with self.subTest(key=key), self.assertRaises(ValueError) as caught:
                hosted.validate_smoke_output(sse(event))
            self.assertNotIn("PRIVATE-MARKER", str(caught.exception))

    def test_duplicate_completions_fail(self):
        with self.assertRaises(ValueError):
            hosted.validate_smoke_output(sse(completion(), completion()))

    def test_malformed_or_conflicting_framing_fails(self):
        for output in (
            'event: response.completed\ndata: {PRIVATE-MARKER\n\n',
            'event: error\ndata: ' + json.dumps(completion()) + "\n\n",
            'event: response.completed\n\n',
            'event: response.completed\ndata: {"type":"response.completed"}\nevent: error\n',
            'event: response.completed\ndata: [DONE]\n\n',
            '{"type":null}\n', 'data: []\n\n',
        ):
            with self.subTest(output=output), self.assertRaises(ValueError) as caught:
                hosted.validate_smoke_output(output)
            self.assertNotIn("PRIVATE-MARKER", str(caught.exception))

    def test_unknown_event_fields_do_not_replace_terminal_validation(self):
        event = completion()
        event["unexpected"] = {"status": "failed"}
        hosted.validate_smoke_output(sse({"type": "response.extension"}, event))
        event["response"]["status"] = "incomplete"
        with self.assertRaises(ValueError):
            hosted.validate_smoke_output(sse(event))

    def test_cli_stdin_success_and_bounded_sanitized_failure(self):
        with patch.object(hosted.sys, "stdin", io.StringIO(sse(completion()))), self.assertLogs(level="INFO") as logs:
            self.assertEqual(0, hosted.main(["--validate-smoke"]))
        self.assertIn("Document retrieval/authorization was not tested", " ".join(logs.output))
        for value in ("PRIVATE-MARKER", "x" * (hosted.MAX_SMOKE_OUTPUT + 1)):
            with patch.object(hosted.sys, "stdin", io.StringIO(value)), self.assertLogs(level="ERROR") as logs:
                self.assertEqual(1, hosted.main(["--validate-smoke"]))
            self.assertNotIn("PRIVATE-MARKER", " ".join(logs.output))

    def test_existing_endpoint_cli_preserved(self):
        with redirect_stdout(io.StringIO()) as output:
            self.assertEqual(0, hosted.main(["--invocations-endpoint", "https://agent.example.test/protocols/invocations"]))
        self.assertEqual("https://agent.example.test/protocols\n", output.getvalue())


if __name__ == "__main__":
    unittest.main()
