#!/usr/bin/env python3
"""
One-time helper: exchange SHOPIFY_API_KEY + SHOPIFY_API_SECRET for a
permanent offline access token.

Usage:
    SHOPIFY_API_KEY=xxx SHOPIFY_API_SECRET=yyy SHOPIFY_SHOP=potero-standard \
        python plugins/shopify/get_token.py

Opens a browser window → you approve the app on your store → the script
prints SHOPIFY_ACCESS_TOKEN. Copy that value into Railway env vars.
"""
from __future__ import annotations

import hashlib
import hmac
import http.server
import os
import secrets
import sys
import threading
import urllib.parse
import webbrowser

try:
    import httpx
except ImportError:
    import subprocess
    subprocess.check_call([sys.executable, "-m", "pip", "install", "-q", "httpx"])
    import httpx

API_KEY = os.environ.get("SHOPIFY_API_KEY", "").strip()
API_SECRET = os.environ.get("SHOPIFY_API_SECRET", "").strip()
SHOP = os.environ.get("SHOPIFY_SHOP", "").strip().rstrip("/")
PORT = 3456
REDIRECT_URI = f"http://localhost:{PORT}/callback"
SCOPES = (
    "read_products,write_products,"
    "read_orders,write_orders,"
    "read_customers,"
    "read_inventory,write_inventory,"
    "read_collections,write_collections,"
    "read_draft_orders"
)

if not API_KEY or not API_SECRET or not SHOP:
    print("ERROR: Set SHOPIFY_API_KEY, SHOPIFY_API_SECRET, and SHOPIFY_SHOP env vars.")
    sys.exit(1)

if not SHOP.endswith(".myshopify.com"):
    SHOP = f"{SHOP}.myshopify.com"

_state = secrets.token_hex(16)
_result: dict = {}
_done = threading.Event()


class _Handler(http.server.BaseHTTPRequestHandler):
    def log_message(self, *_):
        pass

    def do_GET(self):
        parsed = urllib.parse.urlparse(self.path)
        if not parsed.path.startswith("/callback"):
            self._respond(404, "Not found")
            return

        params = dict(urllib.parse.parse_qsl(parsed.query))

        if params.get("state") != _state:
            self._respond(400, "State mismatch — possible CSRF. Try again.")
            _done.set()
            return

        if "error" in params:
            self._respond(400, f"Shopify error: {params['error_description']}")
            _result["error"] = params.get("error_description", params["error"])
            _done.set()
            return

        code = params.get("code", "")
        if not code:
            self._respond(400, "No code in callback.")
            _done.set()
            return

        # Verify HMAC
        hmac_from_shopify = params.pop("hmac", "")
        sorted_params = "&".join(f"{k}={v}" for k, v in sorted(params.items()))
        expected = hmac.new(API_SECRET.encode(), sorted_params.encode(), hashlib.sha256).hexdigest()
        if not hmac.compare_digest(expected, hmac_from_shopify):
            self._respond(400, "HMAC validation failed.")
            _result["error"] = "HMAC mismatch"
            _done.set()
            return

        # Exchange code for token
        resp = httpx.post(
            f"https://{SHOP}/admin/oauth/access_token",
            json={"client_id": API_KEY, "client_secret": API_SECRET, "code": code},
            timeout=15,
        )
        if resp.status_code != 200:
            self._respond(500, f"Token exchange failed: {resp.text}")
            _result["error"] = resp.text
            _done.set()
            return

        token = resp.json().get("access_token", "")
        _result["token"] = token
        self._respond(200, "✅ Success! You can close this tab and return to your terminal.")
        _done.set()

    def _respond(self, status: int, body: str):
        encoded = body.encode()
        self.send_response(status)
        self.send_header("Content-Type", "text/plain; charset=utf-8")
        self.send_header("Content-Length", str(len(encoded)))
        self.end_headers()
        self.wfile.write(encoded)


def main():
    auth_url = (
        f"https://{SHOP}/admin/oauth/authorize"
        f"?client_id={API_KEY}"
        f"&scope={urllib.parse.quote(SCOPES)}"
        f"&redirect_uri={urllib.parse.quote(REDIRECT_URI)}"
        f"&state={_state}"
        f"&grant_options[]=offline"
    )

    server = http.server.HTTPServer(("localhost", PORT), _Handler)
    thread = threading.Thread(target=server.serve_forever, daemon=True)
    thread.start()

    print(f"\nOpening browser to authorize hermes-app on {SHOP} ...")
    print(f"If the browser doesn't open, visit:\n  {auth_url}\n")
    webbrowser.open(auth_url)

    _done.wait(timeout=120)
    server.shutdown()

    if "error" in _result:
        print(f"\nERROR: {_result['error']}")
        sys.exit(1)

    token = _result.get("token", "")
    if not token:
        print("\nERROR: No token received. Did you approve the app in the browser?")
        sys.exit(1)

    print("\n" + "=" * 60)
    print("Add this to Railway env vars:")
    print(f"\n  SHOPIFY_ACCESS_TOKEN={token}")
    print(f"  SHOPIFY_SHOP={SHOP}")
    print("\n" + "=" * 60)


if __name__ == "__main__":
    main()
