# Architecture

`mcpauth` is intentionally small and dependency-free (Python standard library
only). It has three cooperating pieces, all in `mcpauth/core.py`.

## 1. Token store

- `generate_token()` — 256-bit URL-safe token via `secrets.token_urlsafe`, with
  a recognizable `mcpauth_` prefix.
- `make_record(token, label)` — derives a per-token 128-bit salt and a
  PBKDF2-HMAC-SHA256 hash (200k rounds). Only `{id, label, algorithm, rounds,
  salt, hash, created_at}` is persisted — never the plaintext.
- `TokenStore` — JSON-backed list of `TokenRecord`s with atomic save
  (`os.replace`) and best-effort `chmod 600`.

## 2. Auth decision (pure)

- `parse_bearer()` extracts the token from an `Authorization` header.
- `verify_token()` hashes the candidate with **each** record's salt and uses
  `hmac.compare_digest`. It iterates over all records (no early exit) so the
  result isn't distinguishable by timing.
- `decide()` maps a header to an `AuthDecision` with a machine reason:
  `missing_header`, `malformed_header`, `invalid_token`, or `ok`.

These functions are side-effect-free and individually unit-tested.

## 3. Reverse proxy

- `build_server()` / `run_proxy()` build a `ThreadingHTTPServer` whose handler:
  1. computes the auth decision for the request,
  2. on failure → `401` + `WWW-Authenticate: Bearer realm=...` and an audit
     record,
  3. on success → strips hop-by-hop + inbound `Authorization`, adds
     `X-Forwarded-*` and the matched token id, forwards via `urllib.request`,
     and relays the upstream status/headers/body back.
- Every decision is emitted through `audit_sink` (defaults to one-line JSON on
  stdout) as an `AuditEvent`.

## Demo harness

`build_demo_upstream()` + `run_demo()` spin up a fake unauthenticated MCP HTTP
server and the proxy on free ports, then assert no-token → `401` and valid-token
→ `200`. This backs both the `demo` subcommand and the integration tests.

## MCP surface

`mcpauth/mcp_server.py` exposes `mcpauth_verify` and `mcpauth_demo` as MCP tools
when the optional `mcp` package is installed; it imports cleanly without it.
