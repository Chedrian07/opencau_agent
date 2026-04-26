from collections.abc import AsyncIterator
import asyncio
from typing import Annotated

import httpx
from fastapi import APIRouter, Depends, HTTPException, Path, Request, WebSocket, WebSocketDisconnect
from fastapi.responses import Response, StreamingResponse
import websockets

from app.config import Settings, get_settings
from app.schemas.sessions import SESSION_ID_PATTERN

router = APIRouter(tags=["vnc"])
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


@router.api_route("/vnc/sessions/{session_id}/{path:path}", methods=["GET", "POST", "OPTIONS"])
async def proxy_vnc_path(
    session_id: SessionId,
    path: str,
    request: Request,
    settings: Settings = Depends(get_settings),
) -> Response:
    target = f"{settings.sandbox_controller_url.rstrip('/')}/sessions/{session_id}/vnc/{path}"
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
        raise HTTPException(status_code=502, detail={"code": "VNC_PROXY_ERROR"}) from exc

    headers = _filtered_headers(response.headers)
    return StreamingResponse(
        _proxy_stream(response, client),
        status_code=response.status_code,
        headers=headers,
        media_type=response.headers.get("content-type"),
        background=None,
    )


@router.get("/vnc/sessions/{session_id}")
async def proxy_vnc_root(session_id: SessionId) -> Response:
    return Response(status_code=307, headers={"location": f"/vnc/sessions/{session_id}/"})


@router.websocket("/vnc/sessions/{session_id}/{path:path}")
async def proxy_vnc_websocket(
    session_id: SessionId,
    path: str,
    websocket: WebSocket,
    settings: Settings = Depends(get_settings),
) -> None:
    subprotocols = _requested_subprotocols(websocket)
    await websocket.accept(subprotocol=subprotocols[0] if subprotocols else None)
    target = f"{settings.sandbox_controller_url.rstrip('/').replace('http://', 'ws://').replace('https://', 'wss://')}/sessions/{session_id}/vnc/{path}"
    if websocket.url.query:
        target = f"{target}?{websocket.url.query}"

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
