"""The MCP server over stdio, for local clients: `python -m agora_api.mcp`."""

from agora_api.mcp.server import server

server.run()
