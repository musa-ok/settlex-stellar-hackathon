from __future__ import annotations

import json
from typing import Any, Optional

from fastapi import WebSocket


class ConnectionManager:
    """Shared bus: live console + buyer/seller agent mesh."""

    def __init__(self) -> None:
        self.active: list[WebSocket] = []
        self.by_role: dict[str, list[WebSocket]] = {
            "buyer": [],
            "seller": [],
            "console": [],
        }

    async def connect(self, websocket: WebSocket, role: str = "console") -> None:
        await websocket.accept()
        self.active.append(websocket)
        self.by_role.setdefault(role, []).append(websocket)

    def disconnect(self, websocket: WebSocket) -> None:
        if websocket in self.active:
            self.active.remove(websocket)
        for sockets in self.by_role.values():
            if websocket in sockets:
                sockets.remove(websocket)

    async def broadcast(self, payload: dict[str, Any]) -> None:
        dead: list[WebSocket] = []
        data = json.dumps(payload, default=str)
        for ws in self.active:
            try:
                await ws.send_text(data)
            except Exception:
                dead.append(ws)
        for ws in dead:
            self.disconnect(ws)

    async def send_to_role(self, role: str, payload: dict[str, Any]) -> None:
        dead: list[WebSocket] = []
        data = json.dumps(payload, default=str)
        for ws in list(self.by_role.get(role, [])):
            try:
                await ws.send_text(data)
            except Exception:
                dead.append(ws)
        for ws in dead:
            self.disconnect(ws)

    async def relay_agent_offer(self, from_role: str, payload: dict[str, Any]) -> None:
        peer = "seller" if from_role == "buyer" else "buyer"
        envelope = {
            "type": "agent_offer",
            "from": from_role,
            "to": peer,
            "data": payload,
        }
        await self.send_to_role(peer, envelope)
        await self.broadcast({"type": "log_hint", "data": envelope})


ws_manager = ConnectionManager()
