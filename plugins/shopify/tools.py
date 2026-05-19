"""Native Shopify tools for Hermes (registered via plugins/shopify)."""

from __future__ import annotations

import os
from typing import Any

from plugins.shopify.client import (
    ShopifyAPIError,
    ShopifyAuthRequiredError,
    ShopifyClient,
    ShopifyError,
)
from tools.registry import tool_error, tool_result


def _check_shopify_available() -> bool:
    return bool(os.environ.get("SHOPIFY_ACCESS_TOKEN") and os.environ.get("SHOPIFY_SHOP"))


def _client() -> ShopifyClient:
    return ShopifyClient()


def _shopify_tool_error(exc: Exception) -> str:
    if isinstance(exc, ShopifyAuthRequiredError):
        return tool_error(str(exc))
    if isinstance(exc, ShopifyAPIError):
        return tool_error(str(exc), status_code=exc.status_code)
    if isinstance(exc, ShopifyError):
        return tool_error(str(exc))
    return tool_error(f"Shopify tool failed: {type(exc).__name__}: {exc}")


def _coerce_limit(raw: Any, *, default: int = 20) -> int:
    try:
        return max(1, min(50, int(raw)))
    except Exception:
        return default


# ---------------------------------------------------------------------------
# shopify_products
# ---------------------------------------------------------------------------

SHOPIFY_PRODUCTS_SCHEMA = {
    "name": "shopify_products",
    "description": (
        "Manage Shopify store products. Actions: list (search/browse), get (by ID), "
        "create (new product), update (edit existing)."
    ),
    "input_schema": {
        "type": "object",
        "properties": {
            "action": {
                "type": "string",
                "enum": ["list", "get", "create", "update"],
                "description": "Operation to perform.",
            },
            "query": {
                "type": "string",
                "description": "Search query (for list). E.g. 'title:shirt' or 'vendor:Nike'.",
            },
            "limit": {
                "type": "integer",
                "description": "Number of results (1-50, default 20).",
            },
            "status": {
                "type": "string",
                "enum": ["active", "draft", "archived"],
                "description": "Filter by status (for list).",
            },
            "id": {
                "type": "string",
                "description": "Product ID or GID (for get/update).",
            },
            "title": {"type": "string", "description": "Product title (create/update)."},
            "body_html": {"type": "string", "description": "Product description HTML (create/update)."},
            "vendor": {"type": "string", "description": "Product vendor (create/update)."},
            "product_type": {"type": "string", "description": "Product type (create/update)."},
            "tags": {
                "type": "string",
                "description": "Comma-separated tags (create/update).",
            },
            "product_status": {
                "type": "string",
                "enum": ["ACTIVE", "DRAFT", "ARCHIVED"],
                "description": "Product status for create/update.",
            },
            "variants": {
                "type": "array",
                "description": "Variants for create. Each: {price, sku, inventory_quantity, title}.",
                "items": {"type": "object"},
            },
        },
        "required": ["action"],
    },
}

_GQL_PRODUCTS_LIST = """
query ProductsList($first: Int!, $query: String) {
  products(first: $first, query: $query) {
    edges { node {
      id title handle status vendor productType
      totalInventory
      priceRangeV2 {
        minVariantPrice { amount currencyCode }
        maxVariantPrice { amount currencyCode }
      }
      variants(first: 3) { edges { node { id title sku price inventoryQuantity } } }
    }}
    pageInfo { hasNextPage }
  }
}
"""

_GQL_PRODUCT_GET = """
query ProductGet($id: ID!) {
  product(id: $id) {
    id title handle status vendor productType tags bodyHtml
    totalInventory
    priceRangeV2 {
      minVariantPrice { amount currencyCode }
      maxVariantPrice { amount currencyCode }
    }
    variants(first: 100) { edges { node {
      id title sku price compareAtPrice inventoryQuantity barcode
    }}}
    images(first: 5) { edges { node { url altText } } }
  }
}
"""

_GQL_PRODUCT_CREATE = """
mutation ProductCreate($input: ProductInput!) {
  productCreate(input: $input) {
    product { id title handle status }
    userErrors { field message }
  }
}
"""

_GQL_PRODUCT_UPDATE = """
mutation ProductUpdate($input: ProductInput!) {
  productUpdate(input: $input) {
    product { id title handle status }
    userErrors { field message }
  }
}
"""


def _handle_shopify_products(args: dict, **kw) -> str:
    action = str(args.get("action") or "list").strip().lower()
    try:
        c = _client()
        if action == "list":
            q = args.get("query") or None
            status = args.get("status")
            if status:
                q = f"{q} status:{status}".strip() if q else f"status:{status}"
            data = c.graphql(_GQL_PRODUCTS_LIST, {"first": _coerce_limit(args.get("limit")), "query": q})
            edges = data.get("products", {}).get("edges", [])
            products = [e["node"] for e in edges]
            return tool_result({"products": products, "count": len(products),
                                "has_next_page": data.get("products", {}).get("pageInfo", {}).get("hasNextPage", False)})

        if action == "get":
            pid = str(args.get("id") or "").strip()
            if not pid:
                return tool_error("id is required for action='get'")
            data = c.graphql(_GQL_PRODUCT_GET, {"id": c.gid("Product", pid)})
            return tool_result(data.get("product") or {})

        if action == "create":
            title = str(args.get("title") or "").strip()
            if not title:
                return tool_error("title is required for action='create'")
            inp: dict[str, Any] = {"title": title}
            if args.get("body_html"):
                inp["bodyHtml"] = args["body_html"]
            if args.get("vendor"):
                inp["vendor"] = args["vendor"]
            if args.get("product_type"):
                inp["productType"] = args["product_type"]
            if args.get("tags"):
                inp["tags"] = args["tags"]
            if args.get("product_status"):
                inp["status"] = args["product_status"]
            if args.get("variants"):
                inp["variants"] = args["variants"]
            data = c.graphql(_GQL_PRODUCT_CREATE, {"input": inp})
            result = data.get("productCreate", {})
            user_errors = result.get("userErrors", [])
            if user_errors:
                return tool_error("; ".join(f"{e['field']}: {e['message']}" for e in user_errors))
            return tool_result({"success": True, "product": result.get("product")})

        if action == "update":
            pid = str(args.get("id") or "").strip()
            if not pid:
                return tool_error("id is required for action='update'")
            inp: dict[str, Any] = {"id": c.gid("Product", pid)}
            if args.get("title"):
                inp["title"] = args["title"]
            if args.get("body_html"):
                inp["bodyHtml"] = args["body_html"]
            if args.get("vendor"):
                inp["vendor"] = args["vendor"]
            if args.get("product_type"):
                inp["productType"] = args["product_type"]
            if args.get("tags"):
                inp["tags"] = args["tags"]
            if args.get("product_status"):
                inp["status"] = args["product_status"]
            data = c.graphql(_GQL_PRODUCT_UPDATE, {"input": inp})
            result = data.get("productUpdate", {})
            user_errors = result.get("userErrors", [])
            if user_errors:
                return tool_error("; ".join(f"{e['field']}: {e['message']}" for e in user_errors))
            return tool_result({"success": True, "product": result.get("product")})

        return tool_error(f"Unknown shopify_products action: {action}")
    except Exception as exc:
        return _shopify_tool_error(exc)


# ---------------------------------------------------------------------------
# shopify_orders
# ---------------------------------------------------------------------------

SHOPIFY_ORDERS_SCHEMA = {
    "name": "shopify_orders",
    "description": "Browse Shopify orders. Actions: list, get.",
    "input_schema": {
        "type": "object",
        "properties": {
            "action": {
                "type": "string",
                "enum": ["list", "get"],
                "description": "Operation to perform.",
            },
            "query": {
                "type": "string",
                "description": "Search query (for list). E.g. 'financial_status:paid' or customer email.",
            },
            "limit": {"type": "integer", "description": "Number of results (1-50, default 20)."},
            "status": {
                "type": "string",
                "enum": ["open", "closed", "cancelled", "any"],
                "description": "Order status filter (default: open).",
            },
            "id": {"type": "string", "description": "Order ID or GID (for get)."},
        },
        "required": ["action"],
    },
}

_GQL_ORDERS_LIST = """
query OrdersList($first: Int!, $query: String) {
  orders(first: $first, query: $query) {
    edges { node {
      id name displayFinancialStatus displayFulfillmentStatus
      totalPriceSet { shopMoney { amount currencyCode } }
      createdAt updatedAt
      customer { displayName email phone }
      lineItems(first: 10) { edges { node {
        title quantity
        originalUnitPriceSet { shopMoney { amount currencyCode } }
      }}}
      shippingAddress { firstName lastName city province country }
    }}
    pageInfo { hasNextPage }
  }
}
"""

_GQL_ORDER_GET = """
query OrderGet($id: ID!) {
  order(id: $id) {
    id name displayFinancialStatus displayFulfillmentStatus
    totalPriceSet { shopMoney { amount currencyCode } }
    subtotalPriceSet { shopMoney { amount currencyCode } }
    totalTaxSet { shopMoney { amount currencyCode } }
    createdAt updatedAt processedAt
    note tags
    customer { displayName email phone }
    lineItems(first: 50) { edges { node {
      title quantity sku variantTitle
      originalUnitPriceSet { shopMoney { amount currencyCode } }
    }}}
    shippingAddress { firstName lastName address1 address2 city province country zip phone }
    fulfillments { status trackingInfo { company number url } }
  }
}
"""


def _handle_shopify_orders(args: dict, **kw) -> str:
    action = str(args.get("action") or "list").strip().lower()
    try:
        c = _client()
        if action == "list":
            q = args.get("query") or None
            status = args.get("status") or "open"
            if status != "any":
                q = f"{q} status:{status}".strip() if q else f"status:{status}"
            data = c.graphql(_GQL_ORDERS_LIST, {"first": _coerce_limit(args.get("limit")), "query": q})
            edges = data.get("orders", {}).get("edges", [])
            orders = [e["node"] for e in edges]
            return tool_result({"orders": orders, "count": len(orders),
                                "has_next_page": data.get("orders", {}).get("pageInfo", {}).get("hasNextPage", False)})

        if action == "get":
            oid = str(args.get("id") or "").strip()
            if not oid:
                return tool_error("id is required for action='get'")
            data = c.graphql(_GQL_ORDER_GET, {"id": c.gid("Order", oid)})
            return tool_result(data.get("order") or {})

        return tool_error(f"Unknown shopify_orders action: {action}")
    except Exception as exc:
        return _shopify_tool_error(exc)


# ---------------------------------------------------------------------------
# shopify_customers
# ---------------------------------------------------------------------------

SHOPIFY_CUSTOMERS_SCHEMA = {
    "name": "shopify_customers",
    "description": "Browse Shopify customers. Actions: list, search.",
    "input_schema": {
        "type": "object",
        "properties": {
            "action": {
                "type": "string",
                "enum": ["list", "search"],
                "description": "Operation to perform.",
            },
            "query": {
                "type": "string",
                "description": "Search query (required for search). E.g. name, email, or phone.",
            },
            "limit": {"type": "integer", "description": "Number of results (1-50, default 20)."},
        },
        "required": ["action"],
    },
}

_GQL_CUSTOMERS_LIST = """
query CustomersList($first: Int!, $query: String) {
  customers(first: $first, query: $query) {
    edges { node {
      id displayName email phone
      ordersCount
      totalSpentV2 { amount currencyCode }
      createdAt tags
    }}
    pageInfo { hasNextPage }
  }
}
"""


def _handle_shopify_customers(args: dict, **kw) -> str:
    action = str(args.get("action") or "list").strip().lower()
    try:
        c = _client()
        if action in ("list", "search"):
            q = args.get("query") or None
            if action == "search" and not q:
                return tool_error("query is required for action='search'")
            data = c.graphql(_GQL_CUSTOMERS_LIST, {"first": _coerce_limit(args.get("limit")), "query": q})
            edges = data.get("customers", {}).get("edges", [])
            customers = [e["node"] for e in edges]
            return tool_result({"customers": customers, "count": len(customers),
                                "has_next_page": data.get("customers", {}).get("pageInfo", {}).get("hasNextPage", False)})

        return tool_error(f"Unknown shopify_customers action: {action}")
    except Exception as exc:
        return _shopify_tool_error(exc)


# ---------------------------------------------------------------------------
# shopify_collections
# ---------------------------------------------------------------------------

SHOPIFY_COLLECTIONS_SCHEMA = {
    "name": "shopify_collections",
    "description": "Browse Shopify collections. Actions: list, get.",
    "input_schema": {
        "type": "object",
        "properties": {
            "action": {
                "type": "string",
                "enum": ["list", "get"],
                "description": "Operation to perform.",
            },
            "query": {"type": "string", "description": "Search query (for list)."},
            "limit": {"type": "integer", "description": "Number of results (1-50, default 20)."},
            "id": {"type": "string", "description": "Collection ID or GID (for get)."},
        },
        "required": ["action"],
    },
}

_GQL_COLLECTIONS_LIST = """
query CollectionsList($first: Int!, $query: String) {
  collections(first: $first, query: $query) {
    edges { node {
      id title handle
      productsCount { count }
      updatedAt
    }}
    pageInfo { hasNextPage }
  }
}
"""

_GQL_COLLECTION_GET = """
query CollectionGet($id: ID!) {
  collection(id: $id) {
    id title handle descriptionHtml
    productsCount { count }
    products(first: 20) { edges { node { id title handle } } }
    updatedAt
  }
}
"""


def _handle_shopify_collections(args: dict, **kw) -> str:
    action = str(args.get("action") or "list").strip().lower()
    try:
        c = _client()
        if action == "list":
            data = c.graphql(_GQL_COLLECTIONS_LIST, {
                "first": _coerce_limit(args.get("limit")),
                "query": args.get("query") or None,
            })
            edges = data.get("collections", {}).get("edges", [])
            collections = [e["node"] for e in edges]
            return tool_result({"collections": collections, "count": len(collections),
                                "has_next_page": data.get("collections", {}).get("pageInfo", {}).get("hasNextPage", False)})

        if action == "get":
            cid = str(args.get("id") or "").strip()
            if not cid:
                return tool_error("id is required for action='get'")
            data = c.graphql(_GQL_COLLECTION_GET, {"id": c.gid("Collection", cid)})
            return tool_result(data.get("collection") or {})

        return tool_error(f"Unknown shopify_collections action: {action}")
    except Exception as exc:
        return _shopify_tool_error(exc)


# ---------------------------------------------------------------------------
# shopify_graphql
# ---------------------------------------------------------------------------

SHOPIFY_GRAPHQL_SCHEMA = {
    "name": "shopify_graphql",
    "description": (
        "Execute a raw Shopify Admin GraphQL query or mutation. "
        "Use this for operations not covered by the other shopify_* tools."
    ),
    "input_schema": {
        "type": "object",
        "properties": {
            "query": {
                "type": "string",
                "description": "GraphQL query or mutation string.",
            },
            "variables": {
                "type": "object",
                "description": "Optional variables dict for the query.",
            },
        },
        "required": ["query"],
    },
}


def _handle_shopify_graphql(args: dict, **kw) -> str:
    gql = str(args.get("query") or "").strip()
    if not gql:
        return tool_error("query is required")
    try:
        c = _client()
        data = c.graphql(gql, args.get("variables") or None)
        return tool_result(data)
    except Exception as exc:
        return _shopify_tool_error(exc)
