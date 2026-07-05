# Perspective view.json anatomy — authoring rules for AI assistants

A Perspective view is a JSON document with this top-level shape:

```json
{
  "custom": {},
  "params": {},
  "props": { "defaultSize": { "height": 600, "width": 800 } },
  "root": { ... component tree ... }
}
```

- `params` — view input/output parameters (keys become view params).
- `custom` — arbitrary custom properties on the view.
- `props` — view props; `defaultSize` is strongly recommended.
- `root` — REQUIRED. The root container component.

## Component nodes

Every component (including `root`) is:

```json
{
  "type": "ia.container.flex",
  "meta": { "name": "root" },
  "props": { "direction": "column" },
  "children": [ ...only containers have children... ]
}
```

Rules:
1. `type` and `meta.name` are required on every component.
2. Sibling components must have unique `meta.name` values.
3. Only `ia.container.*` types may have `children`.
4. Children of a **flex** container should each carry
   `"position": { "basis": "auto" }` (or `grow`/`shrink`/`basis` values).
5. Children of a **coordinate** container carry
   `"position": { "x": 10, "y": 10, "width": 200, "height": 80 }`.

## Common component types

| type | purpose | key props |
|---|---|---|
| `ia.container.flex` | flexbox container | `direction` ("row"/"column"), `justify`, `alignItems`, `wrap` |
| `ia.container.coord` | coordinate container | `mode` ("fixed"/"percent") |
| `ia.display.label` | text label | `text`, `style.fontSize`, `style.color` |
| `ia.display.gauge` | radial gauge | `value`, `outerAxis.range.high/low` |
| `ia.display.led-display` | numeric LED | `value` |
| `ia.chart.timeseries` | time series chart | `series`, `xAxis`, `yAxes` |
| `ia.input.button` | button | `text`, events via `events` key |
| `ia.input.numeric-entry-field` | numeric input | `value` |
| `ia.input.text-field` | text input | `text` |
| `ia.display.table` | data table | `data` (array of row objects), `columns` |

## Bindings

Bindings live in `propConfig`, keyed by the property path they drive:

```json
{
  "type": "ia.display.label",
  "meta": { "name": "TankLevel" },
  "props": { "text": "" },
  "propConfig": {
    "props.text": {
      "binding": {
        "type": "tag",
        "config": { "mode": "direct", "tagPath": "[default]Tanks/Tank1/Level" }
      }
    }
  }
}
```

Valid binding `type` values: `property`, `expression`, `tag`, `query`, `expr-struct`,
`http`, `tag-history`.

Expression binding example:

```json
"binding": { "type": "expr", ... }
```
— NO. The correct type string is `"expression"`, config: `{ "expression": "{view.params.value} * 2" }`.

## Checklist before deploying

1. `root` exists, has `type` and `meta.name: "root"`.
2. Every component has a unique-in-siblings `meta.name`.
3. Non-containers have no `children`.
4. `defaultSize` set on view `props`.
5. Validate with the `perspective_validate_view` tool BEFORE `perspective_upsert_view`.
6. Start from an `ignition://templates/view/*` resource when possible.
