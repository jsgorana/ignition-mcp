# The mcp-bridge WebDev project

Ignition 8.3's REST API doesn't cover everything: live tag values, tag browsing, tag history,
alarm queries, and project file I/O (needed for Perspective view deployment) all fall outside
it. `ignition-mcp` reaches these through a small gateway-side WebDev project called `mcp-bridge`.

## What it is

A single Ignition project (`mcp-bridge`) containing:

- a project script library, `mcp_bridge_lib`, holding all the logic and security checks
- one WebDev python resource, `api`, whose `doPost` is a one-liner that delegates to the library

It's mounted at `POST /system/webdev/mcp-bridge/api/<endpoint>` and distributed as
`bridge/mcp-bridge.zip` (rebuild it with `python bridge/build_zip.py`). The readable sources live
in `bridge/src/`.

## Security

Every request carries a signed envelope produced by the MCP server:

```json
{ "ts": "<unix seconds>",
  "sig": "hmac_sha256(secret, ts + '.' + payload)",
  "payload": "<json string of the actual request>" }
```

The bridge rejects requests whose timestamp skews more than 300 seconds, verifies the HMAC with
a constant-time compare, and returns a generic `{"ok": false, "code": "auth"}` on any failure
with no further detail. File operations are jailed to `data/projects/`: path traversal via `..`,
absolute paths, or symlink escapes is rejected before any I/O happens.

The shared secret is `IGNITION_BRIDGE_SECRET` on the MCP side and a constant in the
`mcp_bridge_lib` script on the gateway side. They have to match. Never commit the real secret;
the archive ships with a `__BRIDGE_SECRET__` placeholder that gets substituted at install time.

## Automatic install (recommended)

With `IGNITION_ALLOW_WRITES=true` and `IGNITION_BRIDGE_SECRET` set, ask your assistant to run the
`bridge_install` tool. It substitutes your secret into a copy of the archive, imports it as
project `mcp-bridge` via the REST API, triggers a project scan, and verifies the result with a
signed ping. Then run `ignition_diagnose`; the bridge check should come back green.

## Manual install

1. Build the archive with your secret baked in:
   ```bash
   python bridge/build_zip.py
   # then substitute the secret in the extracted mcp_bridge_lib/code.py, or edit it after import
   ```
2. In the Ignition Designer or gateway, import `bridge/mcp-bridge.zip` as a new project.
3. Open the `mcp_bridge_lib` script and set `BRIDGE_SECRET = '<your secret>'`, replacing the
   `__BRIDGE_SECRET__` placeholder, then save.
4. Confirm the endpoint responds:
   ```bash
   curl -s -X POST -H 'Content-Type: application/json' -d '{}' \
     http://localhost:8088/system/webdev/mcp-bridge/api/ping
   # -> {"ok": false, "code": "auth", ...}   (correct: unsigned requests are rejected)
   ```
5. Set the same value as `IGNITION_BRIDGE_SECRET` in your MCP client config.

## Endpoints

All are `POST` and all require the signed envelope described above.

| Endpoint | Purpose |
|---|---|
| `ping` | version and capability list |
| `tags/browse`, `tags/read`, `tags/write`, `tags/configure` | tag operations |
| `history/query`, `history/providers` | tag history |
| `alarms/status`, `alarms/journal`, `alarms/ack` | alarms |
| `db/named-query`, `db/query` | database access |
| `files/list`, `files/read`, `files/write`, `files/delete` | project files, jailed to `data/projects/` |
| `trial/reset` | reset the gateway trial timer, for development gateways running under a trial license |

## Troubleshooting

**`bridge_install` reports `verified: false`, or `bridge_status` claims the secret doesn't match
right after a fresh install.**

This points to a platform quirk observed on 8.3 early-access builds: after
`POST /data/api/v1/projects/import/{name}`, the gateway's served project files are correct
(confirmed via `project_export`), but the already-loaded Jython script module for
`mcp_bridge_lib` doesn't hot-reload, and neither does a full gateway restart. A raw filesystem
write to the resource, followed by a project scan, does force a reload reliably. If you have
filesystem access to the gateway:

```bash
# Replace the placeholder (or old secret) directly in the deployed file:
sed -i '' "s/BRIDGE_SECRET = '.*'/BRIDGE_SECRET = 'YOUR_SECRET'/" \
  /path/to/ignition/data/projects/mcp-bridge/ignition/script-python/mcp_bridge_lib/code.py

curl -X POST http://GATEWAY:8088/data/api/v1/scan/projects \
  -H "X-Ignition-API-Token: name:secret"
```

Wait a few seconds, then re-run `bridge_status`. Without filesystem access to a remote gateway,
open the project in Designer, open the `mcp_bridge_lib` script, and save it even with no changes.
Designer saves go through a different code path that does trigger the reload.

**403 on everything.** See the API-key permission fix in the README: the key's auto-created
security level needs to be added to both Gateway Read and Write Permissions.

## Compatibility

Targets and is tested on Ignition 8.3 with the WebDev module active. The bridge declares
`BRIDGE_VERSION`; the MCP server declares a minimum supported version and surfaces mismatches in
`ignition_diagnose`.
