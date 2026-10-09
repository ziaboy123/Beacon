"""Minimal async Source RCON client.

Same ~50-line protocol Umbros's own rcon.py implements, ported independently
here so Beacon has no dependency on the Umbros project.

Packet format: int32 length (LE) | int32 request id (LE) | int32 type (LE)
| null-terminated payload | extra null byte.
"""

import asyncio
import struct

_TYPE_AUTH = 3
_TYPE_AUTH_RESPONSE = 2
_TYPE_COMMAND = 2


class RCONError(Exception):
    pass


class RCONClient:
    def __init__(self, host: str, port: int, password: str, timeout: float = 5.0):
        self.host = host
        self.port = port
        self.password = password
        self.timeout = timeout
        self._reader: asyncio.StreamReader | None = None
        self._writer: asyncio.StreamWriter | None = None
        self._request_id = 0

    async def connect(self) -> None:
        self._reader, self._writer = await asyncio.wait_for(
            asyncio.open_connection(self.host, self.port), timeout=self.timeout
        )
        req_id = await self._send(_TYPE_AUTH, self.password)
        resp_id, _resp_type, _payload = await self._recv()
        if resp_id != req_id:
            raise RCONError("RCON authentication failed (bad password)")

    async def close(self) -> None:
        if self._writer is not None:
            self._writer.close()
            try:
                await self._writer.wait_closed()
            except Exception:
                pass

    def _next_id(self) -> int:
        self._request_id += 1
        return self._request_id

    async def _send(self, pkt_type: int, payload: str) -> int:
        assert self._writer is not None
        req_id = self._next_id()
        body = struct.pack("<ii", req_id, pkt_type) + payload.encode("utf-8") + b"\x00\x00"
        packet = struct.pack("<i", len(body)) + body
        self._writer.write(packet)
        await self._writer.drain()
        return req_id

    async def _recv(self) -> tuple[int, int, str]:
        assert self._reader is not None
        length_bytes = await asyncio.wait_for(self._reader.readexactly(4), timeout=self.timeout)
        (length,) = struct.unpack("<i", length_bytes)
        data = await asyncio.wait_for(self._reader.readexactly(length), timeout=self.timeout)
        req_id, resp_type = struct.unpack("<ii", data[:8])
        payload = data[8:-2].decode("utf-8", errors="replace")
        return req_id, resp_type, payload

    async def command(self, cmd: str) -> str:
        await self._send(_TYPE_COMMAND, cmd)
        _req_id, _resp_type, payload = await self._recv()
        return payload


async def run(host: str, port: int, password: str, cmd: str, timeout: float = 5.0) -> str:
    client = RCONClient(host, port, password, timeout=timeout)
    try:
        await client.connect()
        return await client.command(cmd)
    finally:
        await client.close()
