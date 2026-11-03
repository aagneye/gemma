#!/usr/bin/env python3
"""Carry one TCP port into a network namespace through a unix socket, so agent runs inside `unshare -rn` (no internet,
user decision 2026-11-03) still reach the vLLM server on the host's 127.0.0.1. Used by netns_run.sh.

  host side:  python3 netns_bridge.py host <socket> 127.0.0.1:8000   (listens on the unix socket, connects to the server)
  ns side:    python3 netns_bridge.py ns 8000 <socket>                (listens on 127.0.0.1:8000 inside the namespace)
"""
import asyncio, os, sys


async def pipe(reader, writer):
    try:
        while data := await reader.read(65536):
            writer.write(data); await writer.drain()
    finally:
        writer.close()


async def splice(reader, writer, connect):
    try:
        r2, w2 = await connect()
    except OSError:
        writer.close(); return
    await asyncio.gather(pipe(reader, w2), pipe(r2, writer), return_exceptions=True)


async def main():
    mode = sys.argv[1]
    if mode == "host":
        path, (host, port) = sys.argv[2], sys.argv[3].rsplit(":", 1)
        if os.path.exists(path): os.unlink(path)
        srv = await asyncio.start_unix_server(lambda r, w: splice(r, w, lambda: asyncio.open_connection(host, int(port))), path=path)
        os.chmod(path, 0o600)
    else:
        port, path = int(sys.argv[2]), sys.argv[3]
        srv = await asyncio.start_server(lambda r, w: splice(r, w, lambda: asyncio.open_unix_connection(path)), "127.0.0.1", port)
    async with srv:
        await srv.serve_forever()


if __name__ == "__main__":
    asyncio.run(main())
