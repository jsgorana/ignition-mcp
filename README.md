<!-- mcp-name: io.github.jsgorana/ignition-mcp -->
# ignition-mcp

An MCP (Model Context Protocol) server for Inductive Automation Ignition. It gives an AI
assistant, Claude Desktop, Claude Code, or any [MCP client](https://modelcontextprotocol.io),
structured access to an Ignition gateway: browse and write tags, query history and alarms,
manage projects, and deploy full Perspective views.

Tested against Ignition 8.3. 43 tools spanning tags, history, alarms, projects, gateway
administration, and Perspective. The server is read-only by default; every write is gated behind
an explicit opt-in.

```
You:    "Deploy a Perspective dashboard to a new project called LineOverview with a
         gauge bound to [default]Line1/Speed."
Claude: (bootstraps the project, writes the view, wires the tag binding, triggers a scan)
        -> https://gateway:8088/data/perspective/client/LineOverview
```

## Why two planes

Ignition 8.3 ships a native REST API, but it doesn't expose live tag values, tag history, alarm
queries, or Perspective view resources. `ignition-mcp` covers the gap with two transport planes:

- **REST plane.** The gateway's native `/data/api/v1` API, authenticated with an API key, used
  for projects, gateway configuration, modules, logs, backups, and Perspective session
  diagnostics.
- **Bridge plane.** A small WebDev project (`mcp-bridge`) you install once on the gateway. It
  exposes the gateway scripting surface (`system.tag.*`, `system.alarm.*`, `system.db.*`, and
  project file I/O) over HMAC-signed HTTP requests.

Tools that need the bridge degrade with a clear message if it isn't installed. Run
`ignition_diagnose` any time to see what's configured and what's missing.

## Quickstart

### 1. Create an API key on the gateway

Gateway web UI -> Config -> Security -> API Keys -> Create. Give it a name, for example `claude`.
Copy the full token; it looks like `claude:AbCd...`.

The key's auto-created security level (`Authenticated/<key-name>`) needs to be granted gateway
read/write access under Config -> Security -> General -> Gateway Read/Write Permissions. Skip
this step and calls return HTTP 403; `ignition_diagnose` will tell you and give the exact fix.

### 2. Install ignition-mcp

```bash
pipx install ignition-mcp
# or: uvx ignition-mcp
# or: pip install ignition-mcp
```

### 3. Configure your MCP client

Claude Desktop (`claude_desktop_config.json`) or Claude Code (`.mcp.json`):

```json
{
  "mcpServers": {
    "ignition": {
      "command": "ignition-mcp",
      "env": {
        "IGNITION_URL": "http://localhost:8088",
        "IGNITION_API_TOKEN": "claude:YOUR_SECRET_HERE"
      }
    }
  }
}
```

Restart the client and ask it to run `ignition_diagnose`. You should get an all-green checklist,
aside from a warning about the bridge, which is the next step.

### 4. Install the bridge (recommended, needed for live data and Perspective deploys)

Generate a random secret, enable writes, and let the server install the bridge for you:

```json
"env": {
  "IGNITION_URL": "http://localhost:8088",
  "IGNITION_API_TOKEN": "claude:YOUR_SECRET_HERE",
  "IGNITION_BRIDGE_SECRET": "a-long-random-string",
  "IGNITION_ALLOW_WRITES": "true"
}
```

Ask your assistant to install the bridge (this runs the `bridge_install` tool), then run
`ignition_diagnose` again to confirm the bridge check is green. See
[docs/bridge.md](docs/bridge.md) for the manual install path and troubleshooting.

## Configuration

| Variable | Required | Default | Meaning |
|---|---|---|---|
| `IGNITION_URL` | yes | none | Gateway base URL, e.g. `http://localhost:8088` |
| `IGNITION_API_TOKEN` | yes | none | API key, `name:secret` |
| `IGNITION_BRIDGE_SECRET` | no | unset | HMAC secret for the bridge; bridge tools are disabled without it |
| `IGNITION_ALLOW_WRITES` | no | `false` | Master switch for every mutating tool |
| `IGNITION_TLS_VERIFY` | no | `true` | Set to `false` for self-signed dev gateways |
| `IGNITION_TIMEOUT_S` | no | `30` | Per-request timeout, in seconds |
| `IGNITION_TAG_WRITE_ALLOWLIST` | no | unset | Comma-separated glob patterns; tag writes outside them are refused |

## Safety model

- Read-only by default. Mutating tools refuse to run unless `IGNITION_ALLOW_WRITES=true` and the
  call passes `confirm=true`. Your assistant sets `confirm` after you approve the action.
- Destructive operations echo the name back. Deleting a project or view requires re-sending its
  exact name.
- A tag-write allowlist lets you restrict writable tags to specific path globs.
- REST mutations carry the API key's identity into Ignition's own audit log; bridge mutations log
  to the `mcp-bridge` logger. Secrets are never logged or echoed back.
- The bridge's file endpoints are confined to `data/projects/`; nothing outside that tree is
  reachable.

## Tool catalog

| Area | Tools |
|---|---|
| Diagnostics | `ignition_diagnose`, `gateway_info`, `gateway_trial_status`, `gateway_trial_reset` |
| Tags | `tag_browse`, `tag_read`, `tag_write`, `tag_create`, `tag_config_export`, `tag_config_import` |
| History | `history_query`, `history_providers` |
| Alarms | `alarm_status`, `alarm_journal`, `alarm_acknowledge` |
| Projects | `project_list`, `project_get`, `project_create`, `project_delete`, `project_export`, `project_import`, `project_scan` |
| Perspective | `perspective_bootstrap_project`, `perspective_list_views`, `perspective_get_view`, `perspective_upsert_view`, `perspective_delete_view`, `perspective_validate_view`, `perspective_page_config_get/set`, `perspective_session_props_get`, `perspective_style_upsert`, `perspective_list_sessions` |
| Gateway admin | `gateway_modules`, `gateway_logs_query`, `gateway_logger_set_level`, `gateway_backup`, `gateway_performance`, `config_resource_list` |
| Database | `db_run_named_query`, `db_query` |
| Bridge | `bridge_install`, `bridge_status` |

The server also exposes MCP resources the assistant can read to author valid Perspective views:
`ignition://docs/view-schema` and `ignition://templates/view/{flex-basic,coordinate-basic,tag-bound-dashboard}`.

## Building Perspective views

See [docs/perspective-authoring.md](docs/perspective-authoring.md) for the full writeup. In
short: the assistant reads the view-schema resource, starts from a template, validates offline
with `perspective_validate_view`, then deploys with `perspective_upsert_view`, which validates
again, writes the view, and triggers a project scan. A full round-trip example is in
[examples/deploy-dashboard.md](examples/deploy-dashboard.md).

## Development

```bash
git clone https://github.com/jsgorana/ignition-mcp
cd ignition-mcp
python -m venv .venv && source .venv/bin/activate
pip install -e ".[dev]"

ruff check src tests          # lint
pytest tests/unit             # unit tests, no gateway needed
python bridge/build_zip.py    # rebuild the bridge project archive

# Live integration suite (needs a real 8.3 gateway with the bridge installed):
IGNITION_URL=... IGNITION_API_TOKEN=... IGNITION_BRIDGE_SECRET=... \
IGNITION_ALLOW_WRITES=true python tests/live/live_check.py
```

## Acknowledgments

Built on the [Model Context Protocol](https://modelcontextprotocol.io) and its
[Python SDK](https://github.com/modelcontextprotocol/python-sdk), using
[httpx](https://www.python-httpx.org/) for HTTP. The
[ignition-sdk-examples](https://github.com/inductiveautomation/ignition-sdk-examples) repository
was a useful reference while working out how Ignition's module and scripting APIs fit together.

## License

MIT. See [LICENSE](LICENSE).

## Disclaimer

This project is independent and community-built. It is not affiliated with, endorsed by, or
sponsored by Inductive Automation. "Ignition" and "Perspective" are trademarks of Inductive
Automation, LLC, used here only to describe compatibility. Test any write-enabled tool against a
non-production gateway before pointing it at something that matters.
