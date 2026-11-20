"""Shopify client-credentials token exchange (SPEC §8.7). Thin wrapper over tools/integrations/shopify."""
from __future__ import annotations

from tools.integrations import shopify


def available() -> bool:
    return shopify.available()


def get_token() -> str | None:
    """POST https://{shop}/admin/oauth/access_token grant_type=client_credentials. Cached until expiry."""
    return shopify.get_token()


def gql(query: str, variables: dict | None = None) -> dict:
    return shopify.gql(query, variables)
