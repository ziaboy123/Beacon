# Beacon

LAN-only admin dashboard for the `mc.daniyalzia.co.uk` Minecraft server. No
login — meant to run on LXC 200 itself and only be reachable from the home
network. See the plan this was built from for full background.

## Local development (no real Minecraft box needed)

```
python3 -m venv .venv
.venv/bin/pip install -r requirements.txt
.venv/bin/python3 scripts/dev_fixtures.py /tmp/beacon_dev_data   # synthetic data
.venv/bin/python3 scripts/mock_rcon_server.py 25575 devpassword &  # fake RCON
cp .env.example .env   # edit MC_SERVER_DIR to /tmp/beacon_dev_data, RCON_PASSWORD to devpassword
.venv/bin/python3 -m uvicorn app.main:app --port 8090
```

`scripts/dev_fixtures.py` and `scripts/mock_rcon_server.py` are dev/testing
only, not for deployment. The Console tab needs `journalctl` on PATH, which
only exists on Linux — `scripts/devbin/journalctl` is a fake shim for
testing the console tail locally on macOS (`PATH="$(pwd)/scripts/devbin:$PATH" uvicorn ...`).

## Deploying to the real server (LXC 200, `10.68.5.243`)

1. Copy this directory to the box, create a venv, install requirements.
2. Set up `.env` for real: `BEACON_RCON_PASSWORD` should match the
   `rcon.password` already in `server.properties` (Umbros already uses this
   RCON setup — see `Umbros/docs/UMBROS.md`). Confirm `BEACON_SYSTEMD_UNIT`
   matches the real unit name (`mc-ultimaterealm.service` as of writing).
3. Run as its own systemd service (separate from the Minecraft server
   itself), bound to the LXC's LAN address, e.g. `10.68.5.243:8090`.
4. Add a UFW rule scoping that port to the home LAN subnet(s) — defense in
   depth given the box's double-NAT/multi-VLAN setup — and confirm no
   router port-forward exists for it.
5. **Before trusting the Players → inventory view**: pull a real
   `playerdata/<uuid>.dat` from the live world and check `/api/players/<uuid>/inventory`
   against it. The parsing in `app/nbt_utils.py` targets the 1.20.5+
   component-based item schema (confirmed relevant — this server runs
   1.21.11) but was only tested against synthetic fixtures here, not real
   data. If armor/offhand items show up in "Other" instead of their proper
   bucket, the slot-number assumptions need adjusting for this version.
