# Isolate MCP User Data by Authenticated Google Subject

This ExecPlan is a living document. The sections `Progress`, `Surprises & Discoveries`, `Decision Log`, and `Outcomes & Retrospective` must be kept up to date as work proceeds.

This plan follows the repository requirements in `PLANS.md`. A future implementer should be able to start from this file alone, read the named source files, make the described edits, run the listed commands, and observe the expected behavior.

## Purpose / Big Picture

The deployed MCP server is now protected by Google OAuth. Multiple people with Google accounts can configure ChatGPT to use the same Cloud Run MCP endpoint, so the server must stop treating `/app/data/watchlist.csv` and `/app/data/<run timestamp>/...` as global shared user data. After this change, each authenticated Google user gets an isolated watchlist and isolated fetch output directories, while public market-history cache files remain shared to avoid duplicate Yahoo Finance requests and unnecessary storage growth.

The observable outcome is that two authenticated MCP sessions with different Google `sub` values can both add `AAPL` to their own watchlists without seeing each other's entries. A fetch through the MCP server writes quotes and manifests under `data/users/<derived user key>/runs/...`, while daily history cache files are written once under `data/shared/cache/...`. The existing command-line interface remains unchanged: `--watchlist`, `--output`, and `DEFAULT_WATCHLIST_PATH` continue to behave as they do today for local or operator-driven CLI usage.

## Progress

- [x] (2026-05-13 00:00Z) Created this ExecPlan after reading `PLANS.md`, `src/yfinance_watchlist/mcp_server.py`, `src/yfinance_watchlist/cli.py`, `src/yfinance_watchlist/cache.py`, `src/yfinance_watchlist/store.py`, `test/test_mcp_server.py`, and the beginning of `test/test_cli.py`.
- [x] (2026-05-14 00:00Z) Added `src/yfinance_watchlist/mcp_user_data.py` with HMAC-based Google subject key derivation and per-user/shared MCP path resolution.
- [x] (2026-05-14 00:00Z) Extended `run_fetch_workflow` with optional `cache_output_dir` so MCP can write user runs under `data/users/<key>/runs` and shared cache under `data/shared/cache` without changing CLI parser behavior.
- [x] (2026-05-14 00:00Z) Updated MCP tool signatures to remove `watchlist_path` and `output_dir`, and routed file-backed MCP tools through the authenticated user's derived paths.
- [x] (2026-05-14 00:00Z) Added focused MCP tests for tool schemas, user isolation, missing-token rejection, per-user run output, and shared cache output.
- [x] (2026-05-14 00:00Z) Updated `README.md` and `cloudbuild.yaml` for `YFIN_USER_KEY_SECRET` and the new MCP storage layout.
- [x] (2026-05-14 00:00Z) Ran the full unittest suite with `PYTHONPATH=src uv run python -m unittest discover -s test`; 63 tests passed.

## Surprises & Discoveries

- Observation: The current branch is `mcp_server`, and `src/yfinance_watchlist/mcp_server.py` already constructs `GoogleProvider` programmatically from `FASTMCP_SERVER_AUTH_GOOGLE_*` environment variables. This differs from the earlier `master` baseline where the server had no auth provider.
  Evidence: `git status --short --branch` reported `## mcp_server...origin/mcp_server`, and `mcp_server.py` imports `GoogleProvider` plus `get_access_token`.

- Observation: The CLI and MCP currently share `run_fetch_workflow`, and `HistoryCache(output_dir)` writes cache files under the same output root as run manifests. To keep CLI behavior unchanged while sharing MCP cache globally, the fetch workflow needs an optional cache-root parameter rather than a replacement for `--output`.
  Evidence: `src/yfinance_watchlist/cli.py` constructs `cache = HistoryCache(output_dir)`, creates run directories with `_make_run_dir(output_dir)`, and prints `History cache updated under {Path(output_dir) / 'cache' / 'history'}`.

- Observation: FastMCP exposes tool input schemas as `tool.inputSchema`, and after removing MCP path arguments the file-backed tool schemas no longer include `watchlist_path` or `output_dir`.
  Evidence: `test_file_tools_do_not_expose_path_arguments` lists tools through `Client(create_server(tmpdir, auth=None))` and asserts those properties are absent.

## Decision Log

- Decision: Keep the CLI contract unchanged and scope only MCP file access by authenticated user.
  Rationale: The user explicitly clarified that CLI behavior does not need to change. The CLI is useful for local or administrative workflows where explicit `--watchlist` and `--output` paths are still valid. The security problem exists for the hosted multi-user MCP surface, not for a local CLI invocation.
  Date/Author: 2026-05-13 / Codex

- Decision: Remove `watchlist_path` and `output_dir` from MCP tool inputs instead of validating user-supplied paths under a user directory.
  Rationale: Authenticated users should not need to know server filesystem layout, and accepting path arguments creates avoidable path traversal and confused-deputy risk. The server can derive the only valid paths from the authenticated token.
  Date/Author: 2026-05-13 / Codex

- Decision: Store user-owned MCP data under `data/users/<user_key>/`, and store shared public cache under `data/shared/cache/`.
  Rationale: Watchlists, run manifests, and quote output reveal a user's interests and should be private to that user. Historical Yahoo Finance price files are public market data and can be reused safely across users if manifests and watchlists remain private.
  Date/Author: 2026-05-13 / Codex

- Decision: Derive `<user_key>` from provider namespace plus Google `sub`, and do not use raw `sub` as a directory name.
  Rationale: Google `sub` is the stable account identifier available in the access token claims. It is better than email because email can change. However, raw stable account identifiers should not appear in object paths, logs, or returned payloads. A fixed-length derived key avoids leaking the raw identifier and is safe as a path segment.
  Date/Author: 2026-05-13 / Codex

- Decision: Prefer an HMAC-derived user key using a server secret, with a deterministic test path.
  Rationale: A plain hash hides casual readability but is still a stable unsalted fingerprint. HMAC with a server-side secret prevents outsiders from correlating a known `sub` to a bucket path. Tests can set the secret explicitly so expected paths remain deterministic.
  Date/Author: 2026-05-13 / Codex

- Decision: Require `YFIN_USER_KEY_SECRET` when starting the production HTTP server through `main`, while keeping `create_server(..., auth=None)` available for unit tests.
  Rationale: Production should fail clearly if the secret needed for private path derivation is not configured. Unit tests must still be able to construct an in-memory server without real Google credentials.
  Date/Author: 2026-05-14 / Codex

## Outcomes & Retrospective

Implementation is complete for this plan. MCP file-backed tools now derive paths from the authenticated token instead of caller-provided path arguments, user watchlists are isolated by HMAC-derived Google subject keys, MCP fetch runs write under per-user `runs/` directories, and MCP history cache writes under `data/shared/cache`. The CLI parser and CLI output behavior remain unchanged. The full unit test suite passes with 63 tests.

## Context and Orientation

This repository is a Python 3.12 project under `/app`. Application code lives under `src/yfinance_watchlist/`, and tests live under `test/`. The test command used by this repository is:

    cd /app
    PYTHONPATH=src uv run python -m unittest discover -s test

The MCP server is implemented in `src/yfinance_watchlist/mcp_server.py`. MCP means Model Context Protocol, the protocol ChatGPT uses to call server-side tools. FastMCP is the Python library used to expose the MCP tools and perform Google OAuth authentication. The current authenticated branch constructs a `GoogleProvider` and creates `FastMCP("yfinance-watchlist", auth=auth)`. Inside an MCP tool call, `fastmcp.server.dependencies.get_access_token()` returns the authenticated caller's token. For Google OAuth, the token has a `claims` dictionary containing `sub`, the stable Google account subject identifier.

The CLI is implemented in `src/yfinance_watchlist/cli.py`. It defines `DEFAULT_WATCHLIST_PATH = "data/watchlist.csv"` and exposes commands such as `show`, `add`, `remove`, and `fetch`. The `fetch` CLI command requires `--output`; this must remain unchanged. The shared implementation function `run_fetch_workflow(watchlist_path, output_dir, start_year, end_year, ...)` reads a watchlist, fetches quotes and history, creates a timestamped run directory under `output_dir`, writes `quotes.csv` and `manifest.json`, and updates a `HistoryCache`.

The cache is implemented in `src/yfinance_watchlist/cache.py`. `HistoryCache(output_dir)` currently writes under `output_dir/cache/history/<symbol>/<year>.csv` and updates `output_dir/cache/history_index.json`. The cache stores public market history and should be shared for MCP calls after this change.

The file output helper is `src/yfinance_watchlist/store.py`. `FileStore.write_quotes` writes `quotes.csv` under a run directory. `FileStore.write_manifest` writes `manifest.json` under the same run directory.

The MCP tests are in `test/test_mcp_server.py`. They currently verify tool listing, quote serialization, history serialization, watchlist file access under a base directory, fetch output creation, and rejection of file paths outside the base directory. These tests must be revised because MCP callers should no longer provide `watchlist_path` or `output_dir` at all.

The CLI tests are in `test/test_cli.py`. They should remain valid. If any CLI tests need updates, those updates must preserve the current CLI behavior rather than remove `--output` or change `DEFAULT_WATCHLIST_PATH`.

## Target Storage Layout

The MCP server should treat its base directory as the root passed to `create_server(base_dir)` or the process current working directory when no base directory is passed. In Cloud Run this is `/app`. Under that root, MCP data should be organized as:

    data/
      users/
        <user_key>/
          watchlist.csv
          runs/
            2026-05-13T03-45Z/
              quotes.csv
              manifest.json
      shared/
        cache/
          history/
            SPY/
              2026.csv
          history_index.json

`<user_key>` is a filesystem-safe derived identifier. The recommended derivation is:

    identity = "google:" + sub
    user_key = hex_hmac_sha256(YFIN_USER_KEY_SECRET, identity)

Use the full lowercase hex digest or a sufficiently long prefix such as 32 hex characters. Prefer the full digest for simplicity and to avoid collision concerns. The implementation must reject missing or empty `sub`. It must not return or log the raw `sub`.

The environment variable `YFIN_USER_KEY_SECRET` should contain a random server-side secret. In Cloud Run, provide it through Secret Manager with `--set-secrets`, similarly to the Google client secret. Unit tests may set this variable to a fixed string such as `test-user-key-secret`.

If the project owner wants to avoid adding a new secret, the implementation can start with `sha256("google:" + sub)` as a temporary fallback, but the production recommendation remains HMAC with a dedicated secret. If a fallback is implemented, it must be explicitly documented in README as weaker privacy.

## Plan of Work

First, add a small helper module, for example `src/yfinance_watchlist/mcp_user_data.py`. Define a frozen dataclass named `McpUserDataPaths` with fields `data_root`, `user_key`, `user_root`, `watchlist_path`, `runs_root`, and `shared_cache_root`, all as `Path` except `user_key`. Add a function such as `resolve_mcp_user_data_paths(base_dir: Path | str, token: object, secret: str | None = None) -> McpUserDataPaths`. This function should read `token.claims`, require `claims["sub"]`, compute the HMAC-derived key, and return paths under `Path(base_dir).resolve() / "data"`. Do not create directories in this helper unless tests show it simplifies callers; the existing watchlist and file-store code already creates parent directories where needed.

The helper should treat the provider namespace as `"google"` for now because this server uses FastMCP's Google provider. If a future auth provider is added, this can become `issuer + ":" + sub`, but this plan does not require multi-provider support. The helper should raise `ValueError("authenticated Google subject is required")` when the token is missing or has no usable `sub`, and `ValueError("YFIN_USER_KEY_SECRET is required")` when no secret is available. Tests can assert these messages as substrings.

Second, extend `run_fetch_workflow` in `src/yfinance_watchlist/cli.py` with an optional keyword-only parameter for the history cache root. A concrete signature is:

    def run_fetch_workflow(
        watchlist_path: str,
        output_dir: str,
        start_year: int,
        end_year: int,
        fail_fast: bool = False,
        keep_runs: int = DEFAULT_KEEP_RUNS,
        on_error: Callable[[str], None] | None = None,
        cache_output_dir: str | None = None,
    ) -> dict:

Inside the function, construct `HistoryCache(cache_output_dir or output_dir)`. Leave `run_fetch_command` unchanged except that it should not pass `cache_output_dir`, so CLI cache behavior remains exactly as it is today. If the manifest should expose cache location, add a conservative field such as `"cache_root": str(Path(cache_output_dir or output_dir) / "cache")`; otherwise leave manifest shape unchanged except for the fact that MCP paths now point under a user directory.

Third, update `src/yfinance_watchlist/mcp_server.py`. Stop importing `DEFAULT_WATCHLIST_PATH` into this module because MCP no longer uses a public default path. Keep `DEFAULT_KEEP_RUNS`. Add a private helper such as `_current_user_paths(root: Path) -> McpUserDataPaths`, which calls `get_access_token()` and `resolve_mcp_user_data_paths(root, token)`. Each MCP tool that touches user files must call this helper at the beginning of the tool call.

Change the MCP tool signatures and behavior as follows:

    def list_watchlist() -> dict

This reads `paths.watchlist_path`, returns the entries, and includes `watchlist_path` in the result only if useful for debugging. The path must be under `data/users/<user_key>/watchlist.csv`.

    def add_watchlist_symbol(symbol: str, label: str | None = None) -> dict

This writes to `paths.watchlist_path`. It must not accept a path argument.

    def remove_watchlist_symbol(symbol: str) -> dict

This removes from `paths.watchlist_path`. It must not accept a path argument.

    def fetch_watchlist(start_year: int, end_year: int, fail_fast: bool = False, keep_runs: int = DEFAULT_KEEP_RUNS) -> dict

This calls `run_fetch_workflow(str(paths.watchlist_path), str(paths.runs_root), start_year, end_year, fail_fast=fail_fast, keep_runs=keep_runs, cache_output_dir=str(paths.shared_cache_root))`. With the current `HistoryCache` constructor, passing `data/shared` as `cache_output_dir` yields cache files under `data/shared/cache/...`.

Leave `get_quote` and `get_history` as authenticated read-only tools with no per-user file output. They are still protected by server-level auth.

The old `_resolve_relative_path` helper can be removed from `mcp_server.py` if no longer used. If kept, ensure no MCP tool still exposes path arguments.

Fourth, update tests. In `test/test_mcp_server.py`, avoid depending on real Google OAuth for in-memory tests. If needed, update `create_server` to accept an optional `auth_provider` or `auth` argument so tests can create `create_server(tmpdir, auth=None)` while production still uses Google auth by default. For user identity, patch `yfinance_watchlist.mcp_server.get_access_token` to return a simple fake token object with a `claims` dictionary:

    class FakeToken:
        def __init__(self, sub: str) -> None:
            self.claims = {"sub": sub}
            self.scopes = ["openid"]

Set `YFIN_USER_KEY_SECRET` to a fixed value in tests, or pass the secret directly to the helper if the design allows it.

Add or revise tests so they prove these behaviors:

1. `list_tools` still includes `get_quote`, `get_history`, `list_watchlist`, `add_watchlist_symbol`, `remove_watchlist_symbol`, and `fetch_watchlist`.

2. The input schemas for `list_watchlist`, `add_watchlist_symbol`, `remove_watchlist_symbol`, and `fetch_watchlist` no longer expose `watchlist_path` or `output_dir`.

3. Two different fake `sub` values get different watchlists. For example, patch token `user-a`, call `add_watchlist_symbol("AAPL", "Apple")`, then patch token `user-b`, call `list_watchlist`, and expect zero entries. Patch token `user-a` again and expect `AAPL`.

4. Missing token or missing `sub` rejects file-backed MCP tools with an error result. The error text should include `authenticated Google subject is required`.

5. `fetch_watchlist` writes `quotes.csv` and `manifest.json` under `data/users/<derived user key>/runs/<timestamp>/`, while the cache path in each successful `SymbolYearResult` points under `data/shared/cache/history/...`. Mock Yahoo Finance calls as the current tests already do.

6. Path traversal tests are replaced by the stronger assertion that path parameters do not exist. There is no caller-controlled path to traverse.

Leave CLI tests in `test/test_cli.py` passing. Add one focused test if helpful to assert that the CLI `fetch --output <dir>` still writes cache under `<dir>/cache/history` when `cache_output_dir` is not provided.

Fifth, update docs. In `README.md`, revise the MCP Server section so it explains that MCP watchlists and fetch outputs are per authenticated Google user. Mention the layout using `data/users/<derived user key>/...` and `data/shared/cache/...`, but state that `<derived user key>` is not the raw Google `sub`. Preserve the CLI docs and examples using `PYTHONPATH=src uv run python -m yfinance_watchlist.cli ... --output data`; do not remove `--output` from CLI documentation.

Update deployment notes in `cloudbuild.yaml` only if adding `YFIN_USER_KEY_SECRET` to Cloud Run. The deploy step would need an additional `--set-secrets` entry or an appended secret variable in the existing `--set-secrets` argument. The exact syntax must match the current Cloud Build file. If the current file already has:

    --set-secrets
    FASTMCP_SERVER_AUTH_GOOGLE_CLIENT_SECRET=google-client-secret:latest

then extend the second line to:

    FASTMCP_SERVER_AUTH_GOOGLE_CLIENT_SECRET=google-client-secret:latest,YFIN_USER_KEY_SECRET=yfin-user-key-secret:latest

Also document that the Secret Manager secret `yfin-user-key-secret` must exist and that the runtime service account needs permission to access it.

## Concrete Steps

From the repository root `/app`, inspect the current branch and files:

    cd /app
    git status --short --branch
    sed -n '1,220p' src/yfinance_watchlist/mcp_server.py
    sed -n '1,260p' src/yfinance_watchlist/cli.py

Create `src/yfinance_watchlist/mcp_user_data.py` with the dataclass and helper described above. Use only standard library modules such as `dataclasses`, `hashlib`, `hmac`, `os`, `pathlib`, and `typing`.

Patch `src/yfinance_watchlist/cli.py` to add the optional `cache_output_dir` parameter to `run_fetch_workflow` and to construct `HistoryCache(cache_output_dir or output_dir)`. Do not change parser setup, `run_fetch_command`, or `--output` handling.

Patch `src/yfinance_watchlist/mcp_server.py` to use `get_access_token()` and the new helper for all file-backed MCP tools. Remove `watchlist_path` and `output_dir` arguments from MCP tool signatures. Keep the server auth setup already present on the branch unless a testability change is needed, such as optional injected auth for unit tests.

Patch `test/test_mcp_server.py` and, only if necessary, `test/test_cli.py`. Use mocks for Yahoo Finance and fake access tokens so tests remain deterministic and do not call external services.

Run the tests:

    cd /app
    PYTHONPATH=src uv run python -m unittest discover -s test

The expected successful ending is similar to:

    Ran <N> tests in <seconds>s
    OK

If the MCP server import fails because Google OAuth environment variables are not present, fix the testability seam rather than setting real credentials in tests. Unit tests must not require real Google OAuth client IDs or secrets.

## Validation and Acceptance

The implementation is accepted when the full unittest suite passes and the tests demonstrate actual user separation. A human reviewer should be able to read the new `test/test_mcp_server.py` tests and see two different fake Google subjects mapped to different watchlist files.

Manual local validation can be done without real OAuth by using the unit tests. If an authenticated Cloud Run deployment is available, perform a smoke test with an MCP client after deployment:

1. Connect as Google user A and call `add_watchlist_symbol` with `{"symbol": "AAPL", "label": "Apple"}`.
2. Call `list_watchlist` as user A and observe `AAPL`.
3. Connect as Google user B and call `list_watchlist`.
4. Observe that user B does not see user A's `AAPL`.
5. Call `fetch_watchlist` as user A.
6. Inspect the bucket mounted at `/app/data` and observe a run directory under `users/<derived key>/runs/` and history cache under `shared/cache/history/`.

The MCP endpoint should no longer accept `watchlist_path` or `output_dir` in tool calls. If a client sends those fields, FastMCP may ignore or reject them depending on input validation behavior, but `list_tools` must not advertise them.

The CLI remains accepted when existing examples still work, including:

    cd /app
    PYTHONPATH=src uv run python -m yfinance_watchlist.cli fetch --output data --start-year 2026 --end-year 2026

This CLI command should continue to read `data/watchlist.csv` by default and write cache under `data/cache/history`, not `data/shared/cache/history`.

## Idempotence and Recovery

The code changes are additive and safe to retry. Running unit tests creates only temporary directories unless a developer manually invokes the CLI with a real output path.

Do not automatically move or delete existing Cloud Storage data. Existing global files such as `/app/data/watchlist.csv` cannot be assigned to a specific authenticated user without an operator decision. Existing public cache under `/app/data/cache/` may be copied manually to `/app/data/shared/cache/` if desired, but this plan does not require automatic migration. If no cache is migrated, the server will rebuild shared cache files as users fetch history.

If deployment fails after adding `YFIN_USER_KEY_SECRET`, confirm that the Secret Manager secret exists and that `runtime@project-yfin-mcp-server.iam.gserviceaccount.com` has permission to access it. The code should fail fast with a clear message when the secret is missing rather than silently using a raw `sub` path in production.

## Artifacts and Notes

Current relevant branch state at plan creation:

    ## mcp_server...origin/mcp_server
     M .devcontainer/devcontainer.json
    ?? .codex/
    ?? data/
    ?? src/yfinance_watchlist/__pycache__/
    ?? test/__pycache__/
    ?? watchlist.csv

The untracked `data/`, `watchlist.csv`, `.codex/`, and `__pycache__/` entries were present before this plan and should not be treated as part of this work unless the user explicitly asks to clean them.

The current dependency pin at plan creation is:

    fastmcp==3.2.4

This plan assumes the current branch's programmatic `GoogleProvider` setup remains in use. If the project switches back to FastMCP's environment-only auth configuration, re-check the exact FastMCP version and environment variable names before implementation.

Validation transcript from completion:

    PYTHONPATH=src uv run python -m unittest discover -s test
    Ran 63 tests in 0.519s
    OK

## Interfaces and Dependencies

Add `src/yfinance_watchlist/mcp_user_data.py` with these public names:

    @dataclass(frozen=True)
    class McpUserDataPaths:
        data_root: Path
        user_key: str
        user_root: Path
        watchlist_path: Path
        runs_root: Path
        shared_cache_root: Path

    def resolve_mcp_user_data_paths(
        base_dir: Path | str,
        token: object | None,
        secret: str | None = None,
    ) -> McpUserDataPaths:
        ...

    def derive_user_key(sub: str, secret: str, provider: str = "google") -> str:
        ...

`derive_user_key` should compute an HMAC-SHA256 hex digest from the message `provider + ":" + sub` and the provided secret. `resolve_mcp_user_data_paths` should use `os.environ.get("YFIN_USER_KEY_SECRET")` when `secret` is `None`.

Update `src/yfinance_watchlist/cli.py` so `run_fetch_workflow` accepts:

    cache_output_dir: str | None = None

and uses:

    cache = HistoryCache(cache_output_dir or output_dir)

No CLI parser arguments should change.

Update `src/yfinance_watchlist/mcp_server.py` so file-backed MCP tools use:

    paths = _current_user_paths(root)

and never accept path arguments from MCP clients. The final MCP tool surface should be:

    get_quote(symbol: str)
    get_history(symbol: str, start_year: int, end_year: int)
    list_watchlist()
    add_watchlist_symbol(symbol: str, label: str | None = None)
    remove_watchlist_symbol(symbol: str)
    fetch_watchlist(start_year: int, end_year: int, fail_fast: bool = False, keep_runs: int = DEFAULT_KEEP_RUNS)

Revision note, 2026-05-13 / Codex: Initial ExecPlan created to capture the agreed direction: keep CLI behavior unchanged, isolate MCP user data by authenticated Google subject, avoid raw `sub` in paths, and keep public market-history cache shared.

Revision note, 2026-05-14 / Codex: Implementation completed. Updated progress, discoveries, decisions, outcomes, and validation evidence after adding user-scoped MCP paths, shared MCP cache support, tests, README guidance, and Cloud Build secret wiring.
