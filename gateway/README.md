# MCP Gateway

This folder contains the gateway image. It runs the Python MCP gateway and the Secure MCP Tunnel client in one container. Garmin and InBody remain separate upstream MCP servers. The repository root contains the single `docker-compose.yml` that runs Garmin and this gateway; InBody is managed separately.

## Files and setup

- `gateway/`: Python gateway, tool discovery, forwarding, and tunnel startup.
- `Dockerfile`, `requirements.txt`, `scripts/build-image.sh`: gateway-only image build.
- `gateway.yaml.example`: example upstream URLs and token file paths.
- `.env.example`: tunnel ID and runtime key template.
- `gateway.yaml`, `.env`, `secrets/`: local runtime files excluded from Git and Docker images.

From the repository root:

```sh
cp gateway/.env.example gateway/.env
chmod 600 gateway/.env
sh gateway/scripts/copy-upstream-tokens.sh
sh scripts/build-image.sh
sh gateway/scripts/build-image.sh
docker compose up -d
```

Fill `gateway/.env` before starting. The Compose `gateway-init` job creates `gateway/gateway.yaml` and `gateway/secrets/gateway_token` if absent. It does not overwrite existing files. The token copy script copies each upstream's active internal token; do not generate replacements for them. If an upstream token changes, copy it again and restart the gateway.

The gateway uses host networking and listens on `127.0.0.1:18767/mcp`. The default config reaches Garmin at `127.0.0.1:18765` and InBody at `127.0.0.1:18766`. Change `gateway/gateway.yaml` for other hosts or ports. Every request needs `X-MCP-Internal-Token` with the gateway token. The gateway passes each upstream only that upstream's token.

The gateway discovers upstream tools at startup and every 60 seconds. Default `allowed_tools: ["*"]` publishes all tools, including tools that can collect or change data. Public names use `garmin_` and `inbody_` prefixes. Edit `gateway/gateway.yaml` to restrict the list and restart the gateway.

```sh
docker compose ps
docker compose exec -T gateway python -m gateway.combined_healthcheck
curl -sS -o /dev/null -w '%{http_code}\n' http://127.0.0.1:8080/readyz
```

On a new host, set `PUID` and `PGID` in the repository root `.env` to a user able to read `gateway/gateway.yaml` and `gateway/secrets/`. Keep the secrets directory private and token files at mode 600. Build or transfer both Docker images separately; this Compose file only uses local images.
