# Add FastMCP HTTP server for market data tools

This ExecPlan is a living document. The sections `Progress`, `Surprises & Discoveries`, `Decision Log`, and `Outcomes & Retrospective` must be kept up to date as work proceeds.

This document follows `/workspace/PLANS.md`, which defines how ExecPlans in this repository must be written and maintained.

## Purpose / Big Picture

The project currently exposes Yahoo Finance quote, watchlist, and batch fetch behavior through a command-line interface only. After this change, a local MCP client can connect to an HTTP endpoint and call tools for quote lookup, history lookup, watchlist listing, and the same batch fetch workflow that writes `quotes.csv`, `manifest.json`, and yearly cache files. The result is visible by starting the server with `PYTHONPATH=src python -m yfinance_watchlist.mcp_server --host 127.0.0.1 --port 8000 --path /mcp/` and connecting an MCP client to `http://127.0.0.1:8000/mcp/`.

MCP means Model Context Protocol, a JSON-RPC based protocol used by AI clients to call tools exposed by local or remote servers. FastMCP is the Python library already pinned in `requirements.txt`; it provides decorators for registering Python functions as MCP tools and a built-in HTTP transport.

## Progress

- [x] (2026-04-28 00:00Z) Inspected the existing CLI, client, cache, store, watchlist modules, tests, and installed FastMCP signatures.
- [x] (2026-04-28 00:00Z) Decided the first server version will use HTTP transport and expose read plus fetch tools, without watchlist mutation tools.
- [x] (2026-04-28 00:00Z) Refactored fetch execution into `run_fetch_workflow`, which both CLI and MCP can call.
- [x] (2026-04-28 00:00Z) Added `src/yfinance_watchlist/mcp_server.py` with HTTP server startup and four tools.
- [x] (2026-04-28 00:00Z) Added in-process MCP tests for tool listing, quote/history serialization, watchlist reading, fetch outputs, and path rejection.
- [x] (2026-04-28 00:00Z) Updated `README.md` with MCP server usage.
- [x] (2026-04-28 00:00Z) Ran `PYTHONPATH=src python -m unittest discover -s test -v`; all 58 tests passed.

## Surprises & Discoveries

- Observation: `requirements.txt` already pins `fastmcp==3.2.4`, so this feature does not need a dependency addition.
  Evidence: `cat requirements.txt` shows `fastmcp==3.2.4`.

- Observation: The `fastmcp` console script is not on PATH in this environment, but importing the package works and the in-process `fastmcp.Client` can test tools without the console script.
  Evidence: `fastmcp --version` returned `/bin/sh: fastmcp: not found`, while `python -c "import fastmcp; print(fastmcp.__version__)"` printed `3.2.4`.

- Observation: `FastMCP.run` in the installed version delegates HTTP startup to `run_http_async`, whose signature accepts `host`, `port`, and `path`.
  Evidence: `inspect.signature(FastMCP.run_http_async)` showed `host: str | None`, `port: int | None`, and `path: str | None`.

## Decision Log

- Decision: Use FastMCP HTTP transport as the primary server transport.
  Rationale: The user selected an HTTP endpoint, and `FastMCP.run` accepts a transport plus keyword arguments for host, port, and path.
  Date/Author: 2026-04-28 / Codex

- Decision: Expose read and fetch tools only in the first MCP server version.
  Rationale: Quote lookup, history lookup, watchlist listing, and batch fetch satisfy the requested server feature while avoiding remote mutation of `watchlist.csv`.
  Date/Author: 2026-04-28 / Codex

- Decision: Reuse the existing CLI fetch workflow instead of duplicating it in the MCP server.
  Rationale: The CLI already owns cache refresh behavior, manifest construction, and run-directory pruning. One shared workflow keeps CLI and MCP behavior consistent.
  Date/Author: 2026-04-28 / Codex

## Outcomes & Retrospective

Implementation is complete and verified. The package now has a FastMCP HTTP server entrypoint, four MCP tools, safe path handling for file arguments, README usage documentation, and in-process MCP coverage. The full unittest suite passed with 58 tests.

## Context and Orientation

The package lives under `src/yfinance_watchlist`. `src/yfinance_watchlist/client.py` wraps `yfinance` and returns repository-owned dataclasses from `src/yfinance_watchlist/models.py`. `src/yfinance_watchlist/watchlist.py` loads and edits CSV watchlists. `src/yfinance_watchlist/cache.py` stores yearly daily history files under `data/cache/history/<symbol>/<year>.csv` and stores cache metadata in `data/cache/history_index.json`. `src/yfinance_watchlist/cli.py` currently coordinates command-line actions, including the fetch workflow that writes a timestamped run directory under an output root.

An MCP tool is a Python function registered with FastMCP using `@mcp.tool`. A local MCP client can list and call these tools over the configured transport. For tests, FastMCP provides an in-process `Client(server)` so unit tests can exercise tools without starting a real network server.

## Plan of Work

First, refactor `src/yfinance_watchlist/cli.py` so the fetch command delegates to a reusable `run_fetch_workflow` function. This function validates the year range and retention count, loads the watchlist, fetches quotes and yearly history, writes outputs, prunes old run directories, and returns a dictionary containing the manifest payload and paths. `run_fetch_command` will call this function, print the same user-facing output as before, and preserve existing exit codes.

Next, add `src/yfinance_watchlist/mcp_server.py`. It will define `create_server(base_dir: Path | str = Path.cwd()) -> FastMCP`, register tools for `get_quote`, `get_history`, `list_watchlist`, and `fetch_watchlist`, and expose a module-level `mcp = create_server()` for clients that load the module. Its `main` function will parse `--host`, `--port`, and `--path`, then call `mcp.run(transport="http", host=host, port=port, path=path)`.

The MCP server will validate file path arguments before reading or writing. For `watchlist_path` and `output_dir`, it will accept only relative paths under `base_dir`, reject absolute paths, and reject paths that escape `base_dir` through `..`. The CLI will keep its existing path behavior.

Then, add `test/test_mcp_server.py`. The tests will use `fastmcp.Client(create_server(tempdir))` and `unittest.IsolatedAsyncioTestCase` to call the tools in process. The tests will mock Yahoo Finance client methods to avoid network access and verify tool listing, quote serialization, fetch output writing, and path traversal rejection.

Finally, update `README.md` with the server command, endpoint URL, and available MCP tools. Run the full test suite from `/workspace` with `PYTHONPATH=src python -m unittest discover -s test -v`.

## Concrete Steps

From `/workspace`, edit these files:

1. `src/yfinance_watchlist/cli.py`
   Add a reusable fetch workflow function and keep `run_fetch_command` output compatible with the existing CLI.

2. `src/yfinance_watchlist/mcp_server.py`
   Create the FastMCP server, tool registrations, safe path resolver, and HTTP command-line entrypoint.

3. `test/test_mcp_server.py`
   Add in-process MCP tool tests using FastMCP's client.

4. `README.md`
   Document how to start the HTTP MCP server and what tools are available.

Run:

    cd /workspace
    PYTHONPATH=src python -m unittest discover -s test -v

Expected result after implementation:

    Ran 58 tests in 0.506s
    OK

## Validation and Acceptance

Acceptance is behavioral. The full unittest suite must pass. The MCP-specific tests must prove that a client can list the expected tools, call `get_quote` and receive JSON-serializable quote fields, call `fetch_watchlist` and observe a written manifest plus quote CSV, and receive a structured tool error when a path argument tries to escape the configured base directory.

Manual acceptance is to start the server from `/workspace`:

    PYTHONPATH=src python -m yfinance_watchlist.mcp_server --host 127.0.0.1 --port 8000 --path /mcp/

An MCP client should connect to:

    http://127.0.0.1:8000/mcp/

The server should expose `get_quote`, `get_history`, `list_watchlist`, and `fetch_watchlist`.

## Idempotence and Recovery

The implementation is additive and safe to retry. Tests use temporary directories and mocks, so they do not require network access or mutate repository data. If a server process is started manually, stop it with Ctrl-C. If implementation fails midway, rerun the unittest command after each fix and continue from this plan; no destructive migration is involved.

## Artifacts and Notes

The expected default endpoint is:

    http://127.0.0.1:8000/mcp/

The fetch tool returns the same manifest fields that the CLI writes to `manifest.json`, plus `manifest_path` and `quotes_path` so clients can find the generated files.

Validation transcript:

    PYTHONPATH=src python -m unittest discover -s test -v
    ...
    Ran 58 tests in 0.506s
    OK

## Interfaces and Dependencies

Existing dependency:

    fastmcp==3.2.4

New public module:

    yfinance_watchlist.mcp_server

Required functions:

    def create_server(base_dir: Path | str = Path.cwd()) -> FastMCP: ...
    def main(argv: list[str] | None = None) -> int: ...

Required MCP tools:

    get_quote(symbol: str) -> dict
    get_history(symbol: str, start_year: int, end_year: int) -> dict
    list_watchlist(watchlist_path: str = "watchlist.csv") -> dict
    fetch_watchlist(start_year: int, end_year: int, watchlist_path: str = "watchlist.csv", output_dir: str = "data", fail_fast: bool = False, keep_runs: int = 10) -> dict

Revision note: Created on 2026-04-28 to guide implementation of the first FastMCP HTTP server for this project.

Revision note: Updated on 2026-04-28 after implementation to record the completed MCP server, documentation, and passing 58-test validation run.
