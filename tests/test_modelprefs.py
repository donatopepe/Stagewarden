from __future__ import annotations

import tempfile
import unittest
from pathlib import Path

from stagewarden.modelprefs import ModelPreferences


class ModelSelectionPolicyTests(unittest.TestCase):
    def test_manual_selection_and_fallback_policy_round_trip(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp) / "models.json"
            prefs = ModelPreferences.default()
            self.assertEqual(prefs.selection_mode, "manual")
            self.assertFalse(prefs.allow_provider_fallback)
            prefs.selection_mode = "auto"
            prefs.allow_provider_fallback = True
            prefs.allow_paid_provider = True
            prefs.save(path)
            loaded = ModelPreferences.load(path)
            self.assertEqual(loaded.selection_mode, "auto")
            self.assertTrue(loaded.allow_provider_fallback)
            self.assertTrue(loaded.allow_paid_provider)

    def test_invalid_selection_mode_fails_to_manual(self) -> None:
        prefs = ModelPreferences.default()
        prefs.selection_mode = "silent"
        prefs.normalize()
        self.assertEqual(prefs.selection_mode, "manual")

    def test_manual_policy_defaults_to_no_provider_fallback(self) -> None:
        prefs = ModelPreferences.default()
        self.assertEqual(prefs.selection_mode, "manual")
        self.assertFalse(prefs.allow_provider_fallback)
        self.assertFalse(prefs.allow_paid_provider)

    def test_manual_policy_round_trip_preserves_explicit_fallback_authorization(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp) / "models.json"
            prefs = ModelPreferences.default()
            prefs.preferred_model = "cheap"
            prefs.allow_provider_fallback = True
            prefs.save(path)
            loaded = ModelPreferences.load(path)
            self.assertEqual(loaded.selection_mode, "manual")
            self.assertTrue(loaded.allow_provider_fallback)


if __name__ == "__main__":
    unittest.main()
