"""
The API app: REST for the web, and the MCP server at /mcp for agents, over the same services.

    uvicorn agora_api.main:app --port 8000
"""

from contextlib import asynccontextmanager

from fastapi import FastAPI, Request
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse

from agora_api.mcp.server import server as mcp_server
from agora_api.routes.api import router
from agora_api.services.db import NotFound

# Built before the app starts: the MCP session manager exists once its app does.
mcp_app = mcp_server.streamable_http_app(streamable_http_path="/mcp")


@asynccontextmanager
async def lifespan(_: FastAPI):
    async with mcp_server.session_manager.run():
        yield


app = FastAPI(title="Agora API", description="Spanish statistics by territory: the catalogue and its data.", lifespan=lifespan)
# No authentication yet; open to any origin while it's only local.
app.add_middleware(CORSMiddleware, allow_origins=["*"], allow_methods=["GET"], allow_headers=["*"])
app.include_router(router)


@app.exception_handler(NotFound)
async def not_found(_: Request, error: NotFound) -> JSONResponse:
    return JSONResponse({"detail": str(error)}, status_code=404)


@app.exception_handler(ValueError)
async def bad_request(_: Request, error: ValueError) -> JSONResponse:
    return JSONResponse({"detail": str(error)}, status_code=400)


# Last, so the REST routes above take precedence; it answers /mcp.
app.mount("/", mcp_app)
