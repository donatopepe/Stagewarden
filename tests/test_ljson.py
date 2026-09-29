from __future__ import annotations

import tempfile
import unittest
from dataclasses import asdict
from pathlib import Path

from stagewarden.ljson import LJSONOptions, benchmark_sizes, decode, decode_json_bytes, encode, encode_json_bytes, stream_decode, stream_encode
from stagewarden.textcodec import dumps_ascii, to_ascii_safe_text, detect_confusables
from stagewarden.memory import AttemptRecord, MemoryStore


class LJSONTests(unittest.TestCase):
    NON_OBJECT_TRACE = {
        "top-level list": "[1, 2]",
        "top-level string": '"a string"',
        "top-level number": "42",
        "null": "null",
    }

    def test_agent_trace_load_fails_closed_on_non_object_root(self) -> None:
        """A trace file that is not a JSON array must not escape as AttributeError.

        _load_trace_records already handled a missing file and decode errors, but
        its except tuple omitted AttributeError, which is exactly what a non-dict
        root raises, so 4 shapes escaped the agent path.
        """
        from stagewarden.agent import Agent
        from stagewarden.config import AgentConfig

        for label, body in self.NON_OBJECT_TRACE.items():
            with self.subTest(trace=label):
                with tempfile.TemporaryDirectory() as tmp:
                    config = AgentConfig(workspace_root=Path(tmp))
                    config.trace_path.parent.mkdir(parents=True, exist_ok=True)
                    config.trace_path.write_text(body, encoding="utf-8")
                    agent = Agent(config)
                    try:
                        records = agent._load_trace_records()
                    except Exception as exc:  # noqa: BLE001 - the defect under test
                        self.fail(f"trace {label} raised {type(exc).__name__}: {exc}")
                    self.assertEqual(records, [])

    def test_trace_load_already_failing_closed_stays_that_way(self) -> None:
        """Controls: shapes already handled, plus a valid trace round-trip."""
        from stagewarden.agent import Agent
        from stagewarden.config import AgentConfig

        tolerated = {
            "not json": "this is not json",
            "truncated": '{"a":',
            "empty file": "",
        }
        for label, body in tolerated.items():
            with self.subTest(trace=label):
                with tempfile.TemporaryDirectory() as tmp:
                    config = AgentConfig(workspace_root=Path(tmp))
                    config.trace_path.parent.mkdir(parents=True, exist_ok=True)
                    config.trace_path.write_text(body, encoding="utf-8")
                    self.assertEqual(Agent(config)._load_trace_records(), [])
        with tempfile.TemporaryDirectory() as tmp:
            config = AgentConfig(workspace_root=Path(tmp))
            self.assertEqual(Agent(config)._load_trace_records(), [])

    def test_ljson_load_file_stays_strict_for_explicit_cli_paths(self) -> None:
        """load_file must keep raising: a CLI decode of an explicit path should fail.

        This is the counterweight to the agent fix above. Making load_file lenient
        would let `--ljson-decode` silently write an empty file for corrupt input.
        """
        from stagewarden.ljson import load_file

        for label, body in list(self.NON_OBJECT_TRACE.items()) + [
            ("not json", "nope"), ("empty file", "")
        ]:
            with self.subTest(trace=label):
                with tempfile.TemporaryDirectory() as tmp:
                    path = Path(tmp) / "in.ljson"
                    path.write_text(body, encoding="utf-8")
                    with self.assertRaises((ValueError, TypeError, AttributeError)):
                        load_file(path)
        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp) / "absent.ljson"
            with self.assertRaises(OSError):
                load_file(path)

    def test_roundtrip_positional(self) -> None:
        records = [
            {"id": 1, "name": "Mario", "meta": {"city": "Rome"}, "active": True},
            {"id": 2, "name": "Luigi", "meta": {"city": "Milan"}, "active": None},
        ]
        encoded = encode(records)
        self.assertEqual(decode(encoded), records)

    def test_roundtrip_numeric_keys(self) -> None:
        records = [{"id": 1, "name": "Mario"}, {"id": 2, "name": "Luigi"}]
        encoded = encode(records, options=LJSONOptions(numeric_keys=True))
        self.assertEqual(decode(encoded), records)

    def test_missing_fields_normalized_to_null(self) -> None:
        records = [{"id": 1, "name": "Mario"}, {"id": 2}]
        decoded = decode(encode(records))
        self.assertEqual(decoded[1]["name"], None)

    def test_gzip_json_bytes_roundtrip(self) -> None:
        records = [{"id": index, "name": f"user-{index}"} for index in range(10)]
        raw = encode_json_bytes(records, gzip_enabled=True)
        self.assertEqual(decode_json_bytes(raw, gzipped=True), records)

    def test_stream_roundtrip(self) -> None:
        records = [{"id": index, "name": f"user-{index}"} for index in range(7)]
        chunks = list(stream_encode(records, chunk_size=3))
        self.assertEqual(list(stream_decode(chunks)), records)

    def test_benchmark_reduces_size_for_large_dataset(self) -> None:
        records = [{"id": index, "name": f"user-{index}", "role": "member"} for index in range(200)]
        result = benchmark_sizes(records)
        self.assertGreater(result["reduction_percent"], 0.0)

    def test_memory_persistence_uses_ljson(self) -> None:
        with tempfile.TemporaryDirectory() as tmp_dir:
            store = MemoryStore()
            store.attempts.append(
                AttemptRecord(
                    iteration=1,
                    step_id="step-1",
                    model="local",
                    action_type="complete",
                    action_signature="{}",
                    success=True,
                    observation="done",
                )
            )
            path = Path(tmp_dir) / "memory.json"
            store.save(path)
            self.assertIn("attempts_ljson", path.read_text())
            loaded = MemoryStore.load(path)
            self.assertEqual([asdict(item) for item in loaded.attempts], [asdict(item) for item in store.attempts])

    def test_ascii_safe_json_escapes_cross_script_unicode(self) -> None:
        payload = {"latin": "Màrio", "cyrillic": "Привет", "cjk": "你好", "greek": "Ω", "symbol": "€"}
        dumped = dumps_ascii(payload, compact=True)
        self.assertIn(r"\u041f\u0440\u0438\u0432\u0435\u0442", dumped)
        self.assertIn(r"\u4f60\u597d", dumped)
        self.assertIn(r"\u03a9", dumped)
        self.assertIn(r"\u20ac", dumped)

    def test_ascii_safe_text_escapes_ambiguous_chars(self) -> None:
        text = "Màrio Привет 你好 Ω €"
        escaped = to_ascii_safe_text(text)
        self.assertEqual(escaped, r"M\xe0rio \u041f\u0440\u0438\u0432\u0435\u0442 \u4f60\u597d \u03a9 \u20ac")

    def test_confusable_detection_flags_known_homoglyphs(self) -> None:
        warnings = detect_confusables("AΑ eе OО")
        self.assertTrue(any(item.startswith("confusables:") for item in warnings))


if __name__ == "__main__":
    unittest.main()
