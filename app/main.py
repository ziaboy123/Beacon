import os

from fastapi import FastAPI
from fastapi.responses import FileResponse
from fastapi.staticfiles import StaticFiles

from .routers import command, console, icons, players, status, whitelist, world

app = FastAPI(title="Beacon")

app.include_router(status.router)
app.include_router(players.router)
app.include_router(whitelist.router)
app.include_router(command.router)
app.include_router(world.router)
app.include_router(console.router)
app.include_router(icons.router)

_STATIC_DIR = os.path.join(os.path.dirname(__file__), "..", "static")

app.mount("/static", StaticFiles(directory=_STATIC_DIR), name="static")


@app.get("/")
async def index():
    # Always revalidate the shell page so it never serves a stale
    # cached-forever HTML that points at outdated JS/CSS. The static assets
    # it references carry their own ?v= query param, bumped on each
    # deploy, so browsers can still cache those aggressively and safely.
    return FileResponse(
        os.path.join(_STATIC_DIR, "index.html"),
        headers={"Cache-Control": "no-cache"},
    )
