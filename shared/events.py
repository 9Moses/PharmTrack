"""
shared/events.py
Central registry of all RabbitMQ event contracts across PharmTrack microservices.
Import this module in any service to use the canonical event names and schemas.

Exchange topology:
  pharmtrack.auth     (fanout) — auth / OTP events  → all services
  pharmtrack.delivery (topic)  — delivery.*          → notification-service, email-service
  pharmtrack.medicine (topic)  — medicine.*          → delivery-service (future)
"""

# ─── Exchange names ───────────────────────────────────────────
EXCHANGE_AUTH     = "pharmtrack.auth"
EXCHANGE_DELIVERY = "pharmtrack.delivery"
EXCHANGE_MEDICINE = "pharmtrack.medicine"

# ─── Routing keys ─────────────────────────────────────────────

class AuthEvents:
    OTP_REQUESTED  = "otp.requested"
    USER_LOGGED_IN = "user.logged_in"
    USER_LOGGED_OUT = "user.logged_out"


class DeliveryEvents:
    ASSIGNED       = "delivery.assigned"
    SCANNED        = "delivery.scanned"
    STATUS_CHANGED = "delivery.status_changed"
    COMPLETED      = "delivery.completed"
    CANCELLED      = "delivery.cancelled"


class MedicineEvents:
    CREATED        = "medicine.created"
    STOCK_UPDATED  = "medicine.stock_updated"
    LOW_STOCK      = "medicine.low_stock"


# ─── Payload schemas (documentation) ─────────────────────────
"""
otp.requested
  { event, email, name, otp }

user.logged_in
  { event, user_id, email, name, role }

delivery.assigned
  { event, delivery_id, user_id, customer_email, customer_name,
    driver_name, from_location, destination, total_amount, qr_code, items }

delivery.scanned
  { event, delivery_id, user_id, customer_email, customer_name }

delivery.status_changed
  { event, delivery_id, user_id, old_status, new_status,
    customer_email, customer_name, driver_name, destination }

delivery.completed
  { event, delivery_id, user_id, customer_email, customer_name, destination }

delivery.cancelled
  { event, delivery_id, user_id, customer_email, customer_name,
    cancellation_reason }

medicine.created
  { event, medicine_id, name, quantity }

medicine.stock_updated
  { event, medicine_id, name, old_quantity, new_quantity }
"""
