"""Inject credentials into a connection URI at load time.
Keeps .env URIs readable while the password lives in its own encrypted variable."""

from __future__ import annotations

from urllib.parse import quote, urlsplit, urlunsplit


def with_credentials(uri: str, username: str = "", password: str = "") -> str:
    """Return the URI with credentials applied, replacing any already embedded.
    Both parts are percent-encoded, so a password may contain @ : / and friends."""
    if not uri:
        return uri
    if not username and not password:
        return uri

    parts = urlsplit(uri)
    host = parts.netloc.rsplit("@", 1)[-1]

    userinfo = quote(username, safe="")
    if password:
        userinfo = f"{userinfo}:{quote(password, safe='')}"

    return urlunsplit(
        (parts.scheme, f"{userinfo}@{host}" if userinfo else host,
         parts.path, parts.query, parts.fragment)
    )


def strip_credentials(uri: str) -> str:
    """Return the URI without any userinfo, safe to log or display."""
    if not uri:
        return uri
    parts = urlsplit(uri)
    return urlunsplit(
        (parts.scheme, parts.netloc.rsplit("@", 1)[-1], parts.path, parts.query, parts.fragment)
    )
