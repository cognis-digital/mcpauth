# mcpauth — Drop-in token-auth gateway in front of unauthenticated MCP servers

> Part of the **[Cognis Neural Suite](https://github.com/cognis-digital)** by [Cognis Digital](https://cognis.digital)
> Cognis Open Collaboration License (COCL) v1.0 · domain: `ai-security`

[![install](https://img.shields.io/badge/install-git%2B%20%C2%B7%20pipx%20%C2%B7%20uv-6b46c1.svg)](#install--every-way-every-platform)
[![CI](https://github.com/cognis-digital/mcpauth/actions/workflows/ci.yml/badge.svg)](https://github.com/cognis-digital/mcpauth/actions)
[![License: COCL 1.0](https://img.shields.io/badge/License-COCL%201.0-2b6cb0.svg)](LICENSE)
[![Suite](https://img.shields.io/badge/Cognis-Neural%20Suite-6b46c1.svg)](https://github.com/cognis-digital)

**A reverse proxy that adds authentication in front of an existing (unauthenticated) MCP HTTP server.**

*AI Security & Governance — securing LLMs, agents, and the MCP supply chain.*

<!-- cognis:layman:start -->
## What is this?

mcpauth is a security gateway that protects AI tool servers (called MCP servers) by requiring a password before anyone can use them. Many MCP servers ship with no access control at all — anyone who can reach the network port can call every tool. mcpauth sits in front of your existing server and blocks requests that don't carry a valid token, so you decide who gets in. It is aimed at developers and teams who run AI tools internally or over a network and need a simple way to lock them down without modifying the underlying server.
<!-- cognis:layman:end -->

## Why

A large share of MCP servers ship with **no authentication** — if you can reach
the port, you can call every tool. That's fine on `localhost`, but the moment
the server is shared across a team, exposed through a tunnel, or bound to a
non-loopback interface, it becomes an open RPC endpoint into your environment.

`mcpauth` fixes that **without touching the upstream server**. It stands up a
standard-library reverse proxy that:

- requires a valid `Authorization: Bearer <token>` on every request,
- compares the presented token in **constant time** against salted PBKDF2
  hashes (plaintext tokens are never stored),
- forwards authorized requests to the upstream MCP server and streams the
  response back unchanged,
- rejects everything else with `401` and a `WWW-Authenticate` challenge,
- emits a structured JSON **audit record for every auth decision**.

Single-purpose, scriptable, self-hostable, zero pip dependencies.

<!-- cognis:install:start -->
## Install

`mcpauth` is source-available (not published to PyPI) — every method below installs
straight from GitHub. Pick whichever you prefer; the one-line scripts auto-detect
the best tool available on your machine.

**One-liner (Linux / macOS):**
```sh
curl -fsSL https://raw.githubusercontent.com/cognis-digital/mcpauth/HEAD/install.sh | sh
```

**One-liner (Windows PowerShell):**
```powershell
irm https://raw.githubusercontent.com/cognis-digital/mcpauth/HEAD/install.ps1 | iex
```

**Or install manually — any one of:**
```sh
pipx install "git+https://github.com/cognis-digital/mcpauth.git"     # isolated (recommended)
uv tool install "git+https://github.com/cognis-digital/mcpauth.git"  # uv
pip install "git+https://github.com/cognis-digital/mcpauth.git"      # pip
```

**From source:**
```sh
git clone https://github.com/cognis-digital/mcpauth.git
cd mcpauth && pip install .
```

Then run:
```sh
mcpauth --help
```
<!-- cognis:install:end -->

## Install

```bash
pip install "git+https://github.com/cognis-digital/mcpauth.git"
# or, from this repo:
pip install -e ".[dev]"
```

## Quick start

```bash
mcpauth --version

# 1. Generate + store a hashed token (plaintext is shown ONCE):
mcpauth gen-token --tokens tokens.json --label ci-runner

# 2. Put the gateway in front of your unauthenticated MCP server:
mcpauth wrap --upstream http://127.0.0.1:8000 --tokens tokens.json --port 9000

# 3. Clients now authenticate with the token:
curl -i http://127.0.0.1:9000/mcp                          # 401 Unauthorized
curl -i -H "Authorization: Bearer <token>" \
        http://127.0.0.1:9000/mcp                           # 200 OK (forwarded)

# See it end-to-end with a built-in fake upstream:
mcpauth demo
mcpauth mcp   # (via: python -m mcpauth.mcp_server) expose as an MCP server
```

## Subcommands

| Command            | Purpose                                                            |
|--------------------|--------------------------------------------------------------------|
| `gen-token`        | Generate a 256-bit token, store only its salted PBKDF2 hash.       |
| `wrap`             | Run the authenticating reverse proxy in front of `--upstream`.     |
| `list`             | List stored token records (id, label, algo — never the plaintext). |
| `demo`             | Self-contained 401-without / 200-with-token demonstration.         |

All commands accept `--format table|json`.

## How it works

```
        Authorization: Bearer <token>
client ───────────────────────────────▶  mcpauth proxy  ───────────────▶  upstream MCP
                                          │  (no upstream change needed)     (unauthenticated)
       401 + WWW-Authenticate  ◀──────────┤
                                          └─ constant-time hash compare
                                             salted PBKDF2-HMAC-SHA256
                                             one-line JSON audit per decision
```

- **Token storage** — `tokens.json` holds `{id, label, algorithm, rounds, salt,
  hash, ...}` per credential. The plaintext is surfaced exactly once at
  generation and never written to disk.
- **Constant-time compare** — verification hashes the presented token with each
  record's salt and uses `hmac.compare_digest`, checking *every* record so a
  match/non-match isn't revealed by timing.
- **Faithful forwarding** — hop-by-hop headers and the inbound `Authorization`
  are stripped; `X-Forwarded-For`/`-Host` and the matched token id are added.
  Upstream status, headers, and body are relayed back as-is (including non-2xx).

## Built-in demo scenarios

- [`demos/01-basic/`](demos/01-basic/SCENARIO.md) — add auth in front of a fake
  unauthenticated MCP server; show `401` without a token and `200` with one.

## Output formats

- **Table** (default) — human-readable terminal summary.
- **JSON** — machine-readable output for pipelines.
- **Audit log** — one JSON object per line on stdout while `wrap` runs.

## Security notes

- Bind the proxy to `127.0.0.1` (default) unless you intend remote access; for
  internet exposure, terminate TLS at a front proxy or extend with TLS.
- Tokens are bearer credentials — treat `tokens.json` as a secret (the tool
  best-effort `chmod 600`s it) and rotate by regenerating.
- This adds an **authentication** boundary; it is not a WAF and does not inspect
  MCP payloads.

## How it fits the Cognis Neural Suite

`mcpauth` is one tool in the [Cognis Neural Suite](https://github.com/cognis-digital).
Every tool ships an MCP server, so [Cognis.Studio](https://cognis.studio) agents
can call them as scoped capabilities.

**Sibling tools in `ai-security`:** [`mcpharden`](https://github.com/cognis-digital/mcpharden), [`aegis`](https://github.com/cognis-digital/aegis), [`promptmirror`](https://github.com/cognis-digital/promptmirror), [`guardpost`](https://github.com/cognis-digital/guardpost), [`adversa`](https://github.com/cognis-digital/adversa), [`agentlog`](https://github.com/cognis-digital/agentlog), [`ragshield`](https://github.com/cognis-digital/ragshield)

## Contributing

PRs, new detections, and demo scenarios are welcome under the collaboration-pull
model. See the COCL license terms below.

<a name="verification"></a>
## Verification

[![tests](https://img.shields.io/badge/tests-19%20passing-2ea44f.svg)](AUDIT.md)

Every push is verified end-to-end. Latest audit (2026-06-13):

```text
tests        : 19 passed, 0 failed, 0 errored
compile      : all modules parse
cli          : C:\Python314\python.exe: No module named https
package      : https
```

<details><summary>CLI surface (<code>--help</code>)</summary>

```text
C:\Python314\python.exe: No module named https
```
</details>

Full machine-readable results: [`AUDIT.md`](AUDIT.md) · regenerate with `python -m https --help` + `pytest -q`.

<div align="right"><a href="#top">↑ back to top</a></div>


## License

Source-available under the **Cognis Open Collaboration License (COCL) v1.0** —
free for personal, internal-evaluation, research, and educational use;
**commercial / production use requires a license** (licensing@cognis.digital).
See [LICENSE](LICENSE).

## Responsible use

This is dual-use security software. Use it only against systems, data, and
identities you own or are explicitly authorized in writing to test, and in
compliance with applicable law.

## About

**[Cognis Digital](https://cognis.digital)** — Wyoming, USA · *Making Tomorrow
Better Today: Advanced Cybersecurity, AI Innovation, and Blockchain Expertise.*
