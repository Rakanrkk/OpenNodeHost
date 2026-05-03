# SSH Transport Strategy

## Initial strategy

OpenNodeHost will use stdio over SSH as the first transport.

Controller side pattern:

```bash
ssh -T <target> opennodehost-node --stdio
```

This means:
- SSH provides auth + encryption + connectivity
- `opennodehost-node` provides the structured execution protocol
- stdin/stdout carry JSONL request/response/event messages

## Why this approach

Compared with raw SSH command execution, this avoids pushing the entire control protocol through nested shell quoting.

Compared with public WebSocket node services, this avoids exposing a new public control port.

## Future options

Possible future transports:
- SSH local port forwarding to a localhost-only node service
- Unix socket on trusted local systems
- HTTP/gRPC in private networks
