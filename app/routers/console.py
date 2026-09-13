import asyncio

from fastapi import APIRouter, WebSocket, WebSocketDisconnect

from ..config import settings

router = APIRouter()


@router.websocket("/ws/console")
async def console_ws(websocket: WebSocket):
    await websocket.accept()

    try:
        proc = await asyncio.create_subprocess_exec(
            "journalctl", "-u", settings.systemd_unit, "-f", "-n", "200", "-o", "cat",
            stdout=asyncio.subprocess.PIPE,
            stderr=asyncio.subprocess.STDOUT,
        )
    except Exception as exc:
        try:
            await websocket.send_text(f"[beacon] failed to start journalctl: {exc}")
        except Exception:
            pass
        await websocket.close()
        return

    assert proc.stdout is not None

    try:
        while True:
            line = await proc.stdout.readline()
            if not line:
                break
            await websocket.send_text(line.decode("utf-8", errors="replace").rstrip())
    except WebSocketDisconnect:
        pass
    finally:
        proc.terminate()
        try:
            await asyncio.wait_for(proc.wait(), timeout=5)
        except asyncio.TimeoutError:
            proc.kill()
