"""
utils/stock_client.py — Delivery Service
Synchronous HTTP client for querying medicine stock from the gateway.
Called before creating a delivery to validate sufficient quantity.
"""
import logging
import requests
from django.conf import settings

logger = logging.getLogger(__name__)

GATEWAY_URL = getattr(settings, "GATEWAY_INTERNAL_URL", "http://pharmtrack_gateway:8000")
MEDICINES_ENDPOINT = "{}/medicines/{}/"


class InsufficientStockError(Exception):
    """Raised when a medicine does not have enough quantity for the delivery."""
    pass


class StockClientError(Exception):
    """Raised on network or gateway errors during stock validation."""
    pass


def validate_and_fetch_stock(medications: list, auth_token: str) -> list:
    """
    Validates that every medicine in `medications` has sufficient stock.

    Args:
        medications: list of dicts with keys: medicine_id, quantity
        auth_token: the raw JWT token from the incoming request (forwarded to gateway)

    Returns:
        list of enriched dicts: [{medicine_id, quantity, medicine_name, unit_price}, ...]

    Raises:
        InsufficientStockError: if any medicine has insufficient quantity
        StockClientError: if the gateway is unreachable or returns an unexpected error
    """
    headers = {"Authorization": f"Bearer {auth_token}"}
    enriched = []

    for med in medications:
        medicine_id = str(med["medicine_id"])
        requested_qty = int(med.get("quantity", 1))
        url = MEDICINES_ENDPOINT.format(GATEWAY_URL, medicine_id)

        try:
            response = requests.get(url, headers=headers, timeout=5)
        except requests.exceptions.RequestException as exc:
            logger.error("[StockClient] Network error fetching medicine %s: %s", medicine_id, exc)
            raise StockClientError(
                f"Unable to reach gateway to validate medicine {medicine_id}. Please try again."
            ) from exc

        if response.status_code == 404:
            raise InsufficientStockError(f"Medicine {medicine_id} does not exist.")

        if response.status_code != 200:
            logger.error("[StockClient] Gateway returned %s for medicine %s: %s", response.status_code, medicine_id, response.text)
            raise StockClientError(
                f"Unexpected response from gateway (HTTP {response.status_code}) for medicine {medicine_id}."
            )

        data = response.json()
        available_qty = int(data.get("quantity", 0))

        if available_qty < requested_qty:
            raise InsufficientStockError(
                f"Insufficient stock for '{data.get('name', medicine_id)}': "
                f"requested {requested_qty}, available {available_qty}."
            )

        enriched.append({
            "medicine_id": medicine_id,
            "medicine_name": data.get("name", ""),
            "quantity": requested_qty,
            "unit_price": str(data.get("price", "0.00")),
        })

    return enriched
