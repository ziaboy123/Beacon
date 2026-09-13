"""A minimal Source RCON server for local testing only — NOT for deployment.
Lets Beacon's real RCON client be exercised end-to-end without a live
Minecraft server.

Usage: .venv/bin/python3 scripts/mock_rcon_server.py [port] [password]
"""

import asyncio
import struct
import sys

_TYPE_AUTH = 3
_TYPE_AUTH_RESPONSE = 2
_TYPE_RESPONSE_VALUE = 0

RESPONSES = {
    "list": "There are 2 of a max of 20 players online: ziaboy123, CaptainDemise",
    "tps": "TPS from last 1m, 5m, 15m: 19.98, 19.95, 19.9",
    "whitelist reload": "Reloaded the whitelist!",
}


async def _read_packet(reader):
    length_bytes = await reader.readexactly(4)
    (length,) = struct.unpack("<i", length_bytes)
    data = await reader.readexactly(length)
    req_id, pkt_type = struct.unpack("<ii", data[:8])
    payload = data[8:-2].decode("utf-8", errors="replace")
    return req_id, pkt_type, payload


def _make_packet(req_id, pkt_type, payload):
    body = struct.pack("<ii", req_id, pkt_type) + payload.encode("utf-8") + b"\x00\x00"
    return struct.pack("<i", len(body)) + body


async def handle(reader, writer, password):
    authed = False
    try:
        while True:
            req_id, pkt_type, payload = await _read_packet(reader)
            if pkt_type == _TYPE_AUTH:
                authed = payload == password
                resp_id = req_id if authed else -1
                writer.write(_make_packet(resp_id, _TYPE_AUTH_RESPONSE, ""))
                await writer.drain()
                if not authed:
                    break
            else:
                if not authed:
                    break
                cmd = payload.strip()
                base_cmd = cmd.split(" ", 1)[0]
                response = RESPONSES.get(cmd, f"Unknown or executed command: {cmd}")
                print(f"[mock-rcon] ran: {cmd!r} -> {response!r}")
                writer.write(_make_packet(req_id, _TYPE_RESPONSE_VALUE, response))
                await writer.drain()
    except (asyncio.IncompleteReadError, ConnectionResetError):
        pass
    finally:
        writer.close()


async def main(port, password):
    server = await asyncio.start_server(lambda r, w: handle(r, w, password), "127.0.0.1", port)
    print(f"Mock RCON server listening on 127.0.0.1:{port} (password={password!r})")
    async with server:
        await server.serve_forever()


if __name__ == "__main__":
    port = int(sys.argv[1]) if len(sys.argv) > 1 else 25575
    password = sys.argv[2] if len(sys.argv) > 2 else "devpassword"
    asyncio.run(main(port, password))
