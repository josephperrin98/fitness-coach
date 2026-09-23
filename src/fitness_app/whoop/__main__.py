# src/fitness_app/whoop/__main__.py
"""CLI: `auth` (once), `status` (config, token, one live call), `serve`
(default; what .mcp.json runs).

`serve` speaks MCP over stdout, so logging is configured to stderr and
nothing in the serve path may print.
"""

import argparse
import logging
import sys
import time

from fitness_app.env import load_dotenv
from fitness_app.tokenstore import TokenStore
from fitness_app.whoop import auth
from fitness_app.whoop.client import WhoopClient


def cmd_auth(config: auth.WhoopConfig, store: TokenStore, input_fn=input, print_fn=print) -> int:
    state = auth.new_state()
    print_fn("1. Open this URL in your browser and approve access:\n")
    print_fn(auth.authorize_url(config, state) + "\n")
    print_fn("2. Your browser will land on the redirect URI. A 'connection refused'")
    print_fn("   page is expected — nothing is listening there on purpose.")
    pasted = input_fn("3. Paste the full URL from the address bar here: ")
    code = auth.parse_redirect(pasted, state)
    tokens = auth.exchange_code(config, code)
    store.save(auth.PROVIDER, tokens)
    print_fn("Authorised. Tokens saved to", store.path)
    return 0


def cmd_status(config: auth.WhoopConfig, store: TokenStore, print_fn=print) -> int:
    print_fn("config: client id and secret present; redirect uri", config.redirect_uri)
    tokens = store.load(auth.PROVIDER)
    if tokens is None:
        print_fn("token: none.", auth.RELOGIN)
        return 1
    minutes = (tokens.expires_at - time.time()) / 60
    if minutes > 0:
        print_fn(f"token: present, access token expires in {minutes:.0f} min")
    else:
        print_fn("token: present, access token expired (will refresh on next call)")
    profile = WhoopClient(store, config).get_profile()
    print_fn("live call: OK — profile for", profile.get("first_name"), profile.get("last_name"))
    return 0


def cmd_serve(config: auth.WhoopConfig, store: TokenStore) -> int:
    from fitness_app.whoop.server import create_server

    create_server().run()  # stdio transport
    return 0


COMMANDS = {"auth": cmd_auth, "status": cmd_status, "serve": cmd_serve}


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(prog="python -m fitness_app.whoop")
    parser.add_argument("command", nargs="?", default="serve", choices=sorted(COMMANDS))
    args = parser.parse_args(argv)

    logging.basicConfig(
        level=logging.INFO, stream=sys.stderr, format="%(levelname)s %(name)s: %(message)s"
    )
    load_dotenv()
    try:
        config = auth.WhoopConfig.from_env()
    except auth.ConfigError as e:
        print(f"error: {e}", file=sys.stderr)
        return 2

    store = TokenStore()
    try:
        return COMMANDS[args.command](config, store)
    except auth.AuthError as e:
        print(f"error: {e}", file=sys.stderr)
        return 1


if __name__ == "__main__":
    sys.exit(main())
