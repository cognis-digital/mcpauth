"""Hardening tests: edge-case and error-path coverage added during robustness pass."""

from __future__ import annotations

import json
import os
import sys
import tempfile
import unittest

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from mcpauth.cli import main
from mcpauth.core import (
    TokenStore,
    TokenStoreError,
    _MAX_BODY_BYTES,
    _normalize_upstream,
    generate_token,
    make_record,
    verify_token,
)
from mcpauth.mcp_server import verify_capability


class TestTokenStoreLoadEdgeCases(unittest.TestCase):
    """TokenStore.load should reject malformed stores with clear TokenStoreError."""

    def _write(self, tmp, name, content):
        path = os.path.join(tmp, name)
        with open(path, "w", encoding="utf-8") as fh:
            fh.write(content)
        return path

    def test_invalid_json_raises_store_error(self):
        with tempfile.TemporaryDirectory() as tmp:
            path = self._write(tmp, "bad.json", "{not valid json")
            with self.assertRaises(TokenStoreError) as ctx:
                TokenStore.load(path)
            self.assertIn("invalid JSON", str(ctx.exception))

    def test_zero_rounds_raises_store_error(self):
        with tempfile.TemporaryDirectory() as tmp:
            tok = generate_token()
            rec = make_record(tok)
            d = rec.to_dict()
            d["rounds"] = 0
            payload = json.dumps({"tokens": [d]})
            path = self._write(tmp, "tokens.json", payload)
            with self.assertRaises(TokenStoreError) as ctx:
                TokenStore.load(path)
            self.assertIn("rounds", str(ctx.exception))

    def test_negative_rounds_raises_store_error(self):
        with tempfile.TemporaryDirectory() as tmp:
            tok = generate_token()
            rec = make_record(tok)
            d = rec.to_dict()
            d["rounds"] = -1
            payload = json.dumps({"tokens": [d]})
            path = self._write(tmp, "tokens.json", payload)
            with self.assertRaises(TokenStoreError) as ctx:
                TokenStore.load(path)
            self.assertIn("rounds", str(ctx.exception))

    def test_missing_required_field_raises_store_error(self):
        with tempfile.TemporaryDirectory() as tmp:
            # Remove the required 'salt' field.
            tok = generate_token()
            rec = make_record(tok)
            d = rec.to_dict()
            del d["salt"]
            path = self._write(tmp, "tokens.json", json.dumps({"tokens": [d]}))
            with self.assertRaises(TokenStoreError) as ctx:
                TokenStore.load(path)
            self.assertIn("salt", str(ctx.exception))

    def test_non_list_store_raises_store_error(self):
        with tempfile.TemporaryDirectory() as tmp:
            path = self._write(tmp, "tokens.json", json.dumps({"tokens": "oops"}))
            with self.assertRaises(TokenStoreError):
                TokenStore.load(path)

    def test_non_dict_record_raises_store_error(self):
        with tempfile.TemporaryDirectory() as tmp:
            path = self._write(tmp, "tokens.json", json.dumps({"tokens": ["string"]}))
            with self.assertRaises(TokenStoreError):
                TokenStore.load(path)


class TestVerifyTokenEdgeCases(unittest.TestCase):
    """verify_token should skip malformed records rather than crashing."""

    def test_malformed_salt_record_is_skipped(self):
        tok = generate_token()
        good_rec = make_record(tok)
        d = good_rec.to_dict()
        d["salt"] = "not-hex!"
        # Build a fake record-like object from the dict so we can pass it.
        from mcpauth.core import TokenRecord
        bad_rec = TokenRecord(**d)
        # Bad record should be skipped; good token with good record still verifies.
        self.assertIsNotNone(verify_token(tok, [good_rec]))
        # Only the bad record — nothing should match.
        self.assertIsNone(verify_token(tok, [bad_rec]))

    def test_mismatched_hash_length_is_skipped(self):
        tok = generate_token()
        good_rec = make_record(tok)
        d = good_rec.to_dict()
        d["hash"] = "ab"  # way too short — length won't match candidate
        from mcpauth.core import TokenRecord
        bad_rec = TokenRecord(**d)
        self.assertIsNone(verify_token(tok, [bad_rec]))

    def test_empty_token_always_returns_none(self):
        tok = generate_token()
        rec = make_record(tok)
        self.assertIsNone(verify_token("", [rec]))

    def test_empty_records_list_returns_none(self):
        self.assertIsNone(verify_token(generate_token(), []))


class TestNormalizeUpstream(unittest.TestCase):
    def test_empty_upstream_raises(self):
        with self.assertRaises(ValueError):
            _normalize_upstream("")

    def test_whitespace_only_raises(self):
        with self.assertRaises(ValueError):
            _normalize_upstream("   ")

    def test_adds_http_scheme(self):
        self.assertEqual(_normalize_upstream("127.0.0.1:8000"),
                         "http://127.0.0.1:8000")

    def test_strips_trailing_slash(self):
        self.assertEqual(_normalize_upstream("http://127.0.0.1:8000/"),
                         "http://127.0.0.1:8000")

    def test_https_preserved(self):
        self.assertEqual(_normalize_upstream("https://example.com/"),
                         "https://example.com")


class TestCliWrapValidation(unittest.TestCase):
    """CLI wrap subcommand should validate port and timeout before doing I/O."""

    def test_out_of_range_port_exits_2(self):
        # Port -1 is clearly invalid.
        rc = main(["wrap", "--upstream", "http://127.0.0.1:8000",
                   "--port", "-1", "--tokens", "irrelevant.json"])
        self.assertEqual(rc, 2)

    def test_port_too_large_exits_2(self):
        rc = main(["wrap", "--upstream", "http://127.0.0.1:8000",
                   "--port", "99999", "--tokens", "irrelevant.json"])
        self.assertEqual(rc, 2)

    def test_zero_timeout_exits_2(self):
        with tempfile.TemporaryDirectory() as tmp:
            path = os.path.join(tmp, "t.json")
            # Generate a token so the store isn't empty.
            main(["gen-token", "--tokens", path])
            rc = main(["wrap", "--upstream", "http://127.0.0.1:8000",
                       "--timeout", "0", "--tokens", path, "--port", "19191"])
            self.assertEqual(rc, 2)

    def test_negative_timeout_exits_2(self):
        with tempfile.TemporaryDirectory() as tmp:
            path = os.path.join(tmp, "t.json")
            main(["gen-token", "--tokens", path])
            rc = main(["wrap", "--upstream", "http://127.0.0.1:8000",
                       "--timeout", "-5", "--tokens", path, "--port", "19192"])
            self.assertEqual(rc, 2)


class TestCliListMalformedStore(unittest.TestCase):
    def test_malformed_json_exits_2(self):
        with tempfile.TemporaryDirectory() as tmp:
            path = os.path.join(tmp, "bad.json")
            with open(path, "w") as fh:
                fh.write("{broken")
            rc = main(["list", "--tokens", path])
            self.assertEqual(rc, 2)


class TestMcpServerVerifyCapability(unittest.TestCase):
    """verify_capability must never raise — always return a dict."""

    def test_malformed_store_returns_dict_with_store_error(self):
        with tempfile.TemporaryDirectory() as tmp:
            path = os.path.join(tmp, "bad.json")
            with open(path, "w") as fh:
                fh.write("{broken json")
            result = verify_capability("sometoken", path)
            self.assertIsInstance(result, dict)
            self.assertFalse(result.get("allowed"))
            # Should surface a store_error key rather than raising.
            self.assertIn("store_error", result)

    def test_missing_store_returns_rejected_not_error(self):
        # A nonexistent file is intentionally treated as an empty store
        # (normal first-run case), so the token should simply be rejected.
        result = verify_capability("sometoken", "/nonexistent/path/tokens.json")
        self.assertIsInstance(result, dict)
        self.assertFalse(result.get("allowed"))

    def test_valid_in_memory_roundtrip(self):
        # verify_capability with a real store file.
        with tempfile.TemporaryDirectory() as tmp:
            path = os.path.join(tmp, "tokens.json")
            tok = generate_token()
            store = TokenStore(path, [make_record(tok, label="test")])
            store.save()
            result = verify_capability(tok, path)
            self.assertTrue(result["allowed"])
            self.assertEqual(result["reason"], "ok")

    def test_non_string_token_does_not_raise(self):
        # Callers from MCP might pass None or an unexpected type.
        result = verify_capability(None, "/nonexistent/tokens.json")  # type: ignore[arg-type]
        self.assertIsInstance(result, dict)
        self.assertFalse(result.get("allowed"))


class TestBodyCapConstant(unittest.TestCase):
    def test_max_body_bytes_is_sane(self):
        # Ensure the cap is positive and reasonable (at least 1 MB, at most 1 GB).
        self.assertGreater(_MAX_BODY_BYTES, 1024 * 1024)
        self.assertLessEqual(_MAX_BODY_BYTES, 1024 * 1024 * 1024)


if __name__ == "__main__":
    unittest.main()
