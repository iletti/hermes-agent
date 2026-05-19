"""Thin Shopify Admin GraphQL API client used by Hermes native tools."""

from __future__ import annotations

import os
from typing import Any, Optional

import httpx

_API_VERSION = "2025-01"


class ShopifyError(RuntimeError):
    """Base Shopify tool error."""


class ShopifyAuthRequiredError(ShopifyError):
    """Raised when SHOPIFY_ACCESS_TOKEN or SHOPIFY_SHOP is missing."""


class ShopifyAPIError(ShopifyError):
    def __init__(self, message: str, *, status_code: Optional[int] = None) -> None:
        super().__init__(message)
        self.status_code = status_code


def _get_credentials() -> tuple[str, str]:
    token = os.environ.get("SHOPIFY_ACCESS_TOKEN", "").strip()
    shop = os.environ.get("SHOPIFY_SHOP", "").strip().rstrip("/")
    if not token or not shop:
        raise ShopifyAuthRequiredError(
            "Set SHOPIFY_ACCESS_TOKEN and SHOPIFY_SHOP environment variables to use Shopify tools. "
            "Get an access token from your Shopify store: Settings → Apps → Develop apps."
        )
    if not shop.endswith(".myshopify.com"):
        shop = f"{shop}.myshopify.com"
    return token, shop


class ShopifyClient:
    def __init__(self) -> None:
        self._token, self._shop = _get_credentials()
        self._url = f"https://{self._shop}/admin/api/{_API_VERSION}/graphql.json"

    def _headers(self) -> dict[str, str]:
        return {
            "X-Shopify-Access-Token": self._token,
            "Content-Type": "application/json",
        }

    def graphql(self, query: str, variables: Optional[dict[str, Any]] = None) -> dict[str, Any]:
        payload: dict[str, Any] = {"query": query}
        if variables:
            payload["variables"] = variables
        response = httpx.post(self._url, headers=self._headers(), json=payload, timeout=30.0)
        if response.status_code == 401:
            raise ShopifyAPIError(
                "Shopify authentication failed. Check SHOPIFY_ACCESS_TOKEN.", status_code=401
            )
        if response.status_code >= 400:
            raise ShopifyAPIError(
                f"Shopify API returned {response.status_code}: {response.text[:200]}",
                status_code=response.status_code,
            )
        data = response.json()
        if "errors" in data:
            errs = data["errors"]
            if isinstance(errs, list):
                msg = "; ".join(e.get("message", str(e)) for e in errs)
            else:
                msg = str(errs)
            raise ShopifyAPIError(f"Shopify GraphQL error: {msg}")
        return data.get("data", {})

    @staticmethod
    def gid(resource: str, id_or_gid: str) -> str:
        s = str(id_or_gid).strip()
        if s.startswith("gid://"):
            return s
        return f"gid://shopify/{resource}/{s}"
