"""Shopify Admin API integration plugin — bundled, auto-loaded.

Registers 5 tools (products, orders, customers, collections, graphql)
into the ``shopify`` toolset. Auth gated on SHOPIFY_ACCESS_TOKEN and
SHOPIFY_SHOP environment variables.
"""

from __future__ import annotations

from plugins.shopify.tools import (
    SHOPIFY_COLLECTIONS_SCHEMA,
    SHOPIFY_CUSTOMERS_SCHEMA,
    SHOPIFY_GRAPHQL_SCHEMA,
    SHOPIFY_ORDERS_SCHEMA,
    SHOPIFY_PRODUCTS_SCHEMA,
    _check_shopify_available,
    _handle_shopify_collections,
    _handle_shopify_customers,
    _handle_shopify_graphql,
    _handle_shopify_orders,
    _handle_shopify_products,
)

_TOOLS = (
    ("shopify_products",    SHOPIFY_PRODUCTS_SCHEMA,    _handle_shopify_products,    "🛍️"),
    ("shopify_orders",      SHOPIFY_ORDERS_SCHEMA,      _handle_shopify_orders,      "📦"),
    ("shopify_customers",   SHOPIFY_CUSTOMERS_SCHEMA,   _handle_shopify_customers,   "👥"),
    ("shopify_collections", SHOPIFY_COLLECTIONS_SCHEMA, _handle_shopify_collections, "🗂️"),
    ("shopify_graphql",     SHOPIFY_GRAPHQL_SCHEMA,     _handle_shopify_graphql,     "⚡"),
)


def register(ctx) -> None:
    for name, schema, handler, emoji in _TOOLS:
        ctx.register_tool(
            name=name,
            toolset="shopify",
            schema=schema,
            handler=handler,
            check_fn=_check_shopify_available,
            emoji=emoji,
        )
