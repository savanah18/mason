# Build Source
```
git clone https://github.com/litmuschaos/litmus-mcp-server.git

cd litmus-mcp-server
make build
```

```
docker run --rm -it \
  -e CHAOS_CENTER_ENDPOINT=http://your-chaos-center:8080 \
  -e LITMUS_PROJECT_ID=your-project-id \
  -e LITMUS_ACCESS_TOKEN=your-token \
  litmuschaos-mcp-server:latest
```