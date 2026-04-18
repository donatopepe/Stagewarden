from __future__ import annotations

import tempfile
import unittest
from dataclasses import asdict
from pathlib import Path

from stagewarden.ljson import LJSONOptions, benchmark_sizes, decode, decode_json_bytes, encode, encode_json_bytes, stream_decode, stream_encode
from stagewarden.textcodec import dumps_ascii, to_ascii_safe_text, detect_confusables
from stagewarden.memory import AttemptRecord, MemoryStore


class LJSONTests(unittest.TestCase):
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
