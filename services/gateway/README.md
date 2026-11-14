# MCP Gateway service

This folder is the build context for the gateway image. The image contains the Python gateway and the Secure MCP Tunnel client. Garmin has a separate image and InBody is an external upstream.

The repository root `docker-compose.yml` runs one gateway container. There is no init service. Copy `gateway.yaml.example` to `runtime/gateway/gateway.yaml` and edit the upstream addresses. Run `python3 scripts/create-gateway-token.py` from the repository root to create the gateway's own token if missing. Copy the upstreams' active tokens with `sh services/gateway/scripts/copy-upstream-tokens.sh`.

The runtime files are under `runtime/gateway/` and excluded from Git and image builds. The example `gateway.yaml.example` uses Garmin at `127.0.0.1:18765/mcp` and InBody at `127.0.0.1:18766/mcp`. The gateway uses host networking and publishes its own MCP endpoint at `127.0.0.1:18767/mcp`. Every request needs the gateway's `X-MCP-Internal-Token`; each upstream receives only its own token.

The gateway discovers tools at startup and every 60 seconds. Default `allowed_tools: ["*"]` publishes all tools, including data-changing tools. Set specific original tool names in `runtime/gateway/gateway.yaml` to limit exposure. Public names use the upstream ID as a prefix, such as `echo_echo`. Remote private IPv4 HTTP upstreams require `allow_private_http: true` and gateway image 0.4.1 or later. Upstreams must accept `X-MCP-Internal-Token`; Bearer-only authentication is not supported by the current configuration. See [the external MCP guide](../../docs/05-add-upstream-mcp.md).

See the root [README](../../README.md) for build, runtime, and NAS instructions. Files under `docs/` record the earlier standalone gateway project and are historical.
