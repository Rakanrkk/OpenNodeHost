# OpenNodeHost Protocol (Draft)

## Transport

Initial transport:
- stdio-jsonl

One JSON object per line.

## Request envelope

```json
{
  "id": "req-1",
  "method": "ping",
  "params": {}
}
```

## Success response envelope

```json
{
  "id": "req-1",
  "ok": true,
  "result": {}
}
```

## Error response envelope

```json
{
  "id": "req-1",
  "ok": false,
  "error": {
    "type": "not_implemented",
    "message": "..."
  }
}
```

## Event envelope

```json
{
  "event": "node.ready",
  "payload": {}
}
```

## Initial methods

- `ping`
- `node.describe`
- `session.open` (planned)
- `session.close` (planned)
- `exec.start` (planned)
- `exec.status` (planned)
- `exec.read` (planned)
- `exec.interrupt` (planned)
