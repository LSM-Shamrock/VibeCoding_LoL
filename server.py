"""Standalone lobby and authoritative match server (no graphics required)."""
import argparse
from frostbridge.network import GameServer

if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="Frostbridge lobby server")
    parser.add_argument("--host", default="0.0.0.0")
    parser.add_argument("--port", type=int, default=27355)
    args = parser.parse_args()
    server = GameServer(args.host, args.port)
    print(f"Frostbridge listening on {args.host}:{server.port}", flush=True)
    try:
        server.run()
    except KeyboardInterrupt:
        server.stop()
