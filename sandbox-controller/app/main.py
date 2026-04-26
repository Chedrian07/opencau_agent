from collections.abc import AsyncIterator
import asyncio
from typing import Annotated

import httpx
from fastapi import FastAPI, HTTPException, Path, Request, WebSocket, WebSocketDisconnect
from fastapi.responses import Response, StreamingResponse
import websockets

from app.config import Settings, get_settings
from app.docker_sandbox import (
    SandboxStartupError,
    create_sandbox,
    delete_sandbox,
    inspect_sandbox,
    run_allowed_command,
    sandbox_host,
)
from app.schemas import SESSION_ID_PATTERN, CommandRequest, CommandResult, CreateSessionRequest, SessionResponse

app = FastAPI(title="OpenCAU Sandbox Controller", version="0.1.0")
SessionId = Annotated[str, Path(pattern=SESSION_ID_PATTERN)]

HOP_BY_HOP_HEADERS = {
    "connection",
    "keep-alive",
    "proxy-authenticate",
    "proxy-authorization",
    "te",
    "trailers",
    "transfer-encoding",
    "upgrade",
}


def _filtered_headers(headers: httpx.Headers) -> dict[str, str]:
    return {key: value for key, value in headers.items() if key.lower() not in HOP_BY_HOP_HEADERS}


def _requested_subprotocols(websocket: WebSocket) -> list[str]:
    header = websocket.headers.get("sec-websocket-protocol")
    if not header:
        return []
    return [item.strip() for item in header.split(",") if item.strip()]


async def _proxy_stream(response: httpx.Response, client: httpx.AsyncClient) -> AsyncIterator[bytes]:
    try:
        async for chunk in response.aiter_bytes():
            yield chunk
    finally:
        await response.aclose()
        await client.aclose()


@app.get("/health")
async def health() -> dict[str, str]:
    return {"status": "ok"}


@app.post("/sessions", response_model=SessionResponse, status_code=201)
async def create_session(request: CreateSessionRequest) -> SessionResponse:
    settings = get_settings()
    try:
        return create_sandbox(settings, request.session_id)
    except SandboxStartupError as exc:
        raise HTTPException(status_code=504, detail={"code": "SANDBOX_STARTUP_TIMEOUT"}) from exc


@app.get("/sessions/{session_id}", response_model=SessionResponse)
async def get_session(session_id: SessionId) -> SessionResponse:
    return inspect_sandbox(session_id)


@app.delete("/sessions/{session_id}", status_code=204)
async def delete_session(session_id: SessionId) -> None:
    delete_sandbox(session_id)


@app.post("/sessions/{session_id}/commands", response_model=CommandResult)
async def run_command(session_id: SessionId, request: CommandRequest) -> CommandResult:
    return run_allowed_command(session_id, request)


@app.api_route("/sessions/{session_id}/vnc/{path:path}", methods=["GET", "POST", "OPTIONS"])
async def proxy_vnc_http(session_id: SessionId, path: str, request: Request) -> Response:
    host = sandbox_host(session_id)
    if host is None:
        raise HTTPException(status_code=404, detail={"code": "SANDBOX_NOT_FOUND"})
    target = f"http://{host}:6080/{path}"
    if request.url.query:
        target = f"{target}?{request.url.query}"

    client = httpx.AsyncClient(timeout=None)
    outbound = client.build_request(
        request.method,
        target,
        headers={key: value for key, value in request.headers.items() if key.lower() != "host"},
        content=await request.body(),
    )
    try:
        response = await client.send(outbound, stream=True)
    except httpx.HTTPError as exc:
        await client.aclose()
        raise HTTPException(status_code=502, detail={"code": "SANDBOX_VNC_PROXY_ERROR"}) from exc

    return StreamingResponse(
        _proxy_stream(response, client),
        status_code=response.status_code,
        headers=_filtered_headers(response.headers),
        media_type=response.headers.get("content-type"),
    )


@app.websocket("/sessions/{session_id}/vnc/{path:path}")
async def proxy_vnc_websocket(session_id: SessionId, path: str, websocket: WebSocket) -> None:
    host = sandbox_host(session_id)
    if host is None:
        await websocket.close(code=1008)
        return

    subprotocols = _requested_subprotocols(websocket)
    await websocket.accept(subprotocol=subprotocols[0] if subprotocols else None)
    query = websocket.url.query
    target = f"ws://{host}:6080/{path}"
    if query:
        target = f"{target}?{query}"

    try:
        async with websockets.connect(target, max_size=None, subprotocols=subprotocols or None) as upstream:
            async def client_to_upstream() -> None:
                while True:
                    message = await websocket.receive()
                    if "bytes" in message and message["bytes"] is not None:
                        await upstream.send(message["bytes"])
                    elif "text" in message and message["text"] is not None:
                        await upstream.send(message["text"])
                    elif message.get("type") == "websocket.disconnect":
                        await upstream.close()
                        break

            async def upstream_to_client() -> None:
                async for message in upstream:
                    if isinstance(message, bytes):
                        await websocket.send_bytes(message)
                    else:
                        await websocket.send_text(message)

            await asyncio.gather(client_to_upstream(), upstream_to_client())
    except WebSocketDisconnect:
        return
    except Exception:
        await websocket.close(code=1011)
