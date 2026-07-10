import pytest
from unittest.mock import patch
from consumers.delivery_consumer import _deduct_stock, _restore_stock, process_delivery_event
from apps.medicines.models import Medicine


@pytest.mark.django_db
@patch("consumers.delivery_consumer.publish_event")
def test_deduct_stock(mock_publish):
    med = Medicine.objects.create(name="Aspirin", quantity=50, batch="BATCH1", expiry_date="2025-12-31", price=5.0)
    _deduct_stock([{"medicine_id": str(med.id), "quantity": 10}])
    med.refresh_from_db()
    assert med.quantity == 40
    mock_publish.assert_called_once()


@pytest.mark.django_db
@patch("consumers.delivery_consumer.publish_event")
def test_restore_stock(mock_publish):
    med = Medicine.objects.create(name="Aspirin", quantity=50, batch="BATCH1", expiry_date="2025-12-31", price=5.0)
    _restore_stock([{"medicine_id": str(med.id), "quantity": 10}])
    med.refresh_from_db()
    assert med.quantity == 60
    mock_publish.assert_called_once()


@pytest.mark.django_db
@patch("consumers.delivery_consumer._deduct_stock")
def test_process_delivery_event_assigned(mock_deduct):
    process_delivery_event("delivery.assigned", {"event": "delivery.assigned", "items": []})
    mock_deduct.assert_called_once()


@pytest.mark.django_db
@patch("consumers.delivery_consumer._restore_stock")
def test_process_delivery_event_cancelled(mock_restore):
    process_delivery_event("delivery.cancelled", {"event": "delivery.cancelled", "items": []})
    mock_restore.assert_called_once()


def test_process_delivery_event_unknown():
    # Just to cover the else branch
    process_delivery_event("delivery.unknown", {"event": "delivery.unknown"})

