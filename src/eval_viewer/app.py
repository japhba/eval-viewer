"""Flask app factory: bench blueprint at `/`, AO blueprint at `/ao`, plus the
capability-URL access gate and the legacy ao-viewer host redirect."""
from __future__ import annotations

import secrets
from urllib.parse import urlencode

from flask import Flask, abort, make_response, redirect, request

from . import config

_COOKIE_NAME = "_ev_access"
_COOKIE_MAX_AGE = 60 * 60 * 24 * 365  # one year


def create_app() -> Flask:
    from .ao import ao
    from .bench import bench

    app = Flask(__name__)
    app.register_blueprint(bench)
    app.register_blueprint(ao)

    @app.before_request
    def _ao_host_redirect():
        """ao-viewer.janbauer.cc bookmarks predate the unified server; route
        them into the /ao mount with path + query (incl. ?key=) preserved."""
        host = request.host.partition(":")[0]
        if host.startswith("ao-viewer") and not request.path.startswith("/ao"):
            q = request.query_string.decode()
            return redirect("/ao" + request.path + (("?" + q) if q else ""))

    @app.before_request
    def _gate_access():
        """Capability-URL access gate. When a token is set, every request must
        either (a) carry the cookie, or (b) include `?key=<TOKEN>` (which we
        then convert into a cookie + redirect to a clean URL so the token
        doesn't keep showing up in the address bar / referrer / logs)."""
        if config.access_token is None:
            return None
        if request.cookies.get(_COOKIE_NAME) == config.access_token:
            return None
        supplied = request.args.get("key") or request.headers.get("X-Access-Token")
        if supplied and secrets.compare_digest(supplied, config.access_token):
            clean = request.args.to_dict(flat=True)
            clean.pop("key", None)
            target = request.path + (("?" + urlencode(clean)) if clean else "")
            resp = make_response(redirect(target))
            resp.set_cookie(_COOKIE_NAME, config.access_token,
                            max_age=_COOKIE_MAX_AGE, httponly=True, samesite="Lax")
            return resp
        abort(403)

    return app
