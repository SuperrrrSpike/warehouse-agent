from __future__ import annotations

import json
from types import SimpleNamespace
import unittest
from unittest import mock

from warehouse_agent.llm import _summarize_with_openai, summarize_snapshot


class _Response:
    def __init__(self, payload):
        self.payload = payload

    def __enter__(self):
        return self

    def __exit__(self, *args):
        return False

    def read(self):
        return json.dumps(self.payload).encode("utf-8")


def _config():
    return SimpleNamespace(
        openai_api_key="fixture-key",
        openai_model="fixture-model",
        anthropic_api_key=None,
        anthropic_model="fixture-model",
    )


def _snapshot():
    return {
        "backlog_count": 3,
        "empty_run_pct": 25.0,
        "avg_utilization_pct": 55.0,
        "top_congested_stations": [],
    }


class OpenAIResponseTests(unittest.TestCase):
    def test_raw_responses_api_output_is_extracted(self):
        payload = {
            "output": [
                {"type": "reasoning", "summary": []},
                {
                    "type": "message",
                    "content": [
                        {"type": "output_text", "text": "  先处理积压波次。  "}
                    ],
                },
            ]
        }
        with mock.patch(
            "warehouse_agent.llm.urllib.request.urlopen",
            return_value=_Response(payload),
        ):
            result = _summarize_with_openai(_snapshot(), "日报", _config())

        self.assertEqual(result, "先处理积压波次。")

    def test_sdk_compatibility_output_text_is_supported(self):
        with mock.patch(
            "warehouse_agent.llm.urllib.request.urlopen",
            return_value=_Response({"output_text": "  兼容摘要。  "}),
        ):
            result = _summarize_with_openai(_snapshot(), "日报", _config())

        self.assertEqual(result, "兼容摘要。")

    def test_missing_text_falls_back_to_local_summary(self):
        payload = {
            "output": [
                {
                    "type": "message",
                    "content": [{"type": "refusal", "refusal": "fixture"}],
                }
            ]
        }
        with mock.patch(
            "warehouse_agent.llm.urllib.request.urlopen",
            return_value=_Response(payload),
        ):
            result = _summarize_with_openai(_snapshot(), "日报", _config())

        self.assertIn("3个积压任务", result)

    def test_malformed_provider_shape_does_not_break_report(self):
        with mock.patch(
            "warehouse_agent.llm.urllib.request.urlopen",
            return_value=_Response({"output": [None]}),
        ):
            result = summarize_snapshot(
                _snapshot(), provider="openai", mode="日报", config=_config()
            )

        self.assertIn("3个积压任务", result)


if __name__ == "__main__":
    unittest.main()
