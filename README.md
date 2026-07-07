# PharmTrack — Production Microservices Architecture

> Redesigned from a Django monolith into a production-ready, event-driven microservices system.

---

## Architecture Overview

```
┌──────────────────────────────────────────────────────────────────────────┐
│                            CLIENT / FRONTEND                             │
└──────────────────────┬───────────────────────────────────────────────────┘
                       │ HTTPS
          ┌────────────▼────────────┐
          │    GATEWAY SERVICE      │  Django · Port 8000
          │  Auth · Users · Meds   │  JWT (OTP-based) · Redis OTP cache
          │  Vehicles · Audit       │  Publishes → RabbitMQ
          └────────────┬────────────┘
                       │
          ╔════════════▼════════════╗
          ║       RABBITMQ          ║  Port 5672 · Management UI 15672
          ║  pharmtrack.auth        ║  (fanout)
          ║  pharmtrack.delivery    ║  (topic)
          ║  pharmtrack.medicine    ║  (topic)
          ╚══════╤═════════╤════════╝
                 │         │
   ┌─────────────▼──┐  ┌───▼──────────────────┐
   │ DELIVERY SVC   │  │  NOTIFICATION SVC     │
   │ Django · 8001  │  │  Django · 8002        │
   │ Deliveries     │  │  Persists in-app      │
   │ QR Scan/Gen    │  │  notifications to DB  │
   │ Status mgmt    │  │  REST API for UI      │
   └────────────────┘  └──────────────────────┘
                                │
                    ┌───────────▼───────────┐
                    │    EMAIL SERVICE       │
                    │    FastAPI · 8003      │
                    │    aiosmtplib SMTP     │
                    │    Jinja2 templates    │
                    └───────────────────────┘
```

## Services

| Service               | Framework | Port | Database           | Role                                              |
|-----------------------|-----------|------|--------------------|---------------------------------------------------|
| `gateway`             | Django    | 8000 | `gateway_db`       | Auth (OTP+JWT), Users, Medicines, Vehicles, Audit |
| `delivery-service`    | Django    | 8001 | `delivery_db`      | Full delivery lifecycle, QR generation/scan       |
| `notification-service`| Django    | 8002 | `notification_db`  | Persists & serves in-app notifications            |
| `email-service`       | FastAPI   | 8003 | —                  | Async email dispatch via SMTP                     |

## RabbitMQ Exchange Topology

| Exchange              | Type   | Published by    | Consumed by                                  |
|-----------------------|--------|-----------------|----------------------------------------------|
| `pharmtrack.auth`     | fanout | gateway         | delivery-service, notification-service, email-service |
| `pharmtrack.delivery` | topic  | delivery-service| notification-service, email-service          |
| `pharmtrack.medicine` | topic  | gateway         | delivery-service (future)                    |

### Event Routing Keys

```
otp.requested          → email-service (sends OTP email)
user.logged_in         → notification-service (creates login notification)
delivery.assigned      → notification-service + email-service + gateway (stock deduction)
delivery.scanned       → notification-service
delivery.customer_confirmed → notification-service
delivery.status_changed→ notification-service
delivery.completed     → notification-service + email-service
delivery.cancelled     → notification-service + email-service + gateway (stock restoration)
medicine.created       → delivery-service (syncs catalog)
```

---

## Quick Start

### Prerequisites
- Docker ≥ 24
- Docker Compose ≥ 2.20

### 1. Configure secrets

Copy and edit each service's `.env`. The root `.env` holds shared infra credentials.

```bash
# Minimum required changes in each service .env:
#   gateway/.env          → SECRET_KEY, DB_PASSWORD, REDIS_PASSWORD
#   delivery-service/.env → SECRET_KEY, DB_PASSWORD, JWT_SECRET_KEY
#   notification-service/.env → SECRET_KEY, DB_PASSWORD, JWT_SECRET_KEY
#   email-service/.env    → SMTP_USER, SMTP_PASSWORD, DEFAULT_FROM_EMAIL
```

> ⚠️ `JWT_SECRET_KEY` in delivery and notification services must match `SECRET_KEY` in gateway — they share the JWT signing secret for HS256 token validation.

### 2. Start all services

```bash
docker compose up --build -d
```

### 3. Run gateway migrations

```bash
docker compose exec gateway python manage.py migrate
docker compose exec gateway python manage.py createsuperuser
```

### 4. Run delivery and notification migrations

```bash
docker compose exec delivery-service python manage.py migrate
docker compose exec notification-service python manage.py migrate
```

### 5. Verify services

| URL                                    | Description                    |
|----------------------------------------|-------------------------------|
| http://localhost:8000/api/docs/        | Gateway Swagger UI            |
| http://localhost:8001/api/docs/        | Delivery Service Swagger UI   |
| http://localhost:8002/api/docs/        | Notification Service Swagger  |
| http://localhost:8003/docs             | Email Service (FastAPI docs)  |
| http://localhost:8003/health           | Email service health check    |
| http://localhost:15672                 | RabbitMQ Management UI        |

RabbitMQ credentials: `pharmtrack` / `pharmtrack_secret`

---

## API Reference

### Gateway — Authentication

```
POST /auth/request-otp/     { "email": "admin@example.com" }
POST /auth/verify-otp/      { "email": "...", "otp": "123456" }
POST /auth/logout/          { "refresh": "<token>" }   (Bearer required)
POST /auth/token/refresh/   { "refresh": "<token>" }
```

### Gateway — Users

```
GET  /users/           List all users         (superadmin)
POST /users/           Create user            (superadmin)
GET  /users/me/        Current user profile   (authenticated)
GET  /users/<id>/      Get user by ID         (admin+)
PATCH /users/<id>/     Update user            (admin+)
DELETE /users/<id>/    Deactivate user        (admin+)
```

### Gateway — Medicines

```
GET    /medicines/        List medicines
POST   /medicines/        Create medicine
GET    /medicines/<id>/   Get medicine
PATCH  /medicines/<id>/   Update medicine
DELETE /medicines/<id>/   Delete medicine
```

### Gateway — Vehicles

```
/vehicles/vehicles/    CRUD vehicles
/vehicles/drivers/     CRUD drivers
/vehicles/customers/   CRUD customers
```

### Delivery Service

```
GET  /deliveries/                  List deliveries
POST /deliveries/assign/           Assign new delivery
POST /deliveries/scan/             Scan QR code (Driver)
POST /deliveries/<id>/confirm/     Confirm delivery (Customer)
GET  /deliveries/<id>/             Get delivery detail
PATCH /deliveries/<id>/status/     Update delivery status
```

### Notification Service

```
GET   /notifications/               List user notifications
PATCH /notifications/read-all/      Mark all as read
PATCH /notifications/<id>/read/     Mark single as read
```

### Email Service

```
GET  /health    Service health (consumer thread alive check)
POST /send      Manual email trigger (internal/testing)
```

---

## Event Flow Examples

### Login Flow
```
1. Client → POST /auth/request-otp/  (gateway)
2. Gateway stores OTP in Redis
3. Gateway publishes otp.requested → pharmtrack.auth
4. email-service consumes → sends OTP email via SMTP
5. Client → POST /auth/verify-otp/   (gateway)
6. Gateway validates OTP, issues JWT
7. Gateway publishes user.logged_in → pharmtrack.auth
8. notification-service consumes → creates login notification
```

### Delivery Assigned Flow
```
1. Admin → POST /deliveries/assign/  (delivery-service, Bearer JWT)
2. delivery-service synchronously checks stock via HTTP GET to gateway-service
3. delivery-service creates Delivery + DeliveryItems in Postgres
4. Generates encrypted QR code, uploads to Cloudinary
5. Publishes delivery.assigned → pharmtrack.delivery
6. gateway-service consumes → atomically deducts medicine stock
7. notification-service consumes → creates in-app notification
8. email-service consumes → sends assignment email to customer
```

### Delivery Completed Flow
```
1. Driver scans QR → POST /deliveries/scan/  (delivery-service)
2. Status updated to in_transit, delivery.scanned event published
3. Admin → PATCH /deliveries/<id>/status/ { "status": "delivered" }
4. delivery.completed event published
5. notification-service → creates "Delivery Completed" notification
6. email-service → sends completion email to customer
```

### Delivery Cancelled Flow
```
1. Admin → PATCH /deliveries/<id>/status/ { "status": "cancelled" }
2. delivery.cancelled event published (with items snapshot)
3. gateway-service consumes → atomically restores medicine stock
4. notification-service → creates "Delivery Cancelled" notification
5. email-service → sends cancellation email to customer
```

### Delivery Customer Confirmed Flow
```
1. Customer scans QR → POST /deliveries/<id>/confirm/ (delivery-service)
2. Status updated to delivered, delivery.customer_confirmed event published
3. notification-service consumes → creates "Customer Confirmed" notification

---

## Security

- **JWT (HS256)**: Issued by gateway. Downstream services validate tokens statelessly using a shared signing key via a custom `MicroserviceJWTAuthentication` class (avoids local database lookups for users).
- **OTP**: 6-digit code, 5-minute TTL, stored in Redis, rate-limited to 5 req/min.
- **Token Blacklisting**: Refresh tokens are blacklisted on logout via SimpleJWT's token blacklist app.
- **Role-Based Access**: `admin` and `superadmin` roles enforced via DRF permission classes.
- **Encrypted QR**: AES-256-CBC encryption with PKCS7 padding; QR payload is not readable without the shared `QR_SECRET_KEY`.
- **RabbitMQ**: Durable exchanges and queues; persistent message delivery mode.
- **Per-service databases**: Each service owns its data — no shared database.

---

## Production Checklist

- [ ] Replace all `SECRET_KEY` values with strong random strings (≥50 chars)
- [ ] Replace all `DB_PASSWORD` values
- [ ] Replace `SMTP_USER` and `SMTP_PASSWORD` with real credentials or SES/Sendgrid
- [ ] Set `DEBUG=False` in all services
- [ ] Configure `CORS_ALLOWED_ORIGINS` to your frontend domain(s)
- [ ] Set `RABBITMQ_USER`/`RABBITMQ_PASS` to non-default values
- [ ] Enable TLS on RabbitMQ (`amqps://`) for inter-service encryption
- [ ] Add Nginx reverse proxy in front of gateway (port 80/443)
- [ ] Configure SSL certificates (Let's Encrypt or managed cert)
- [ ] Set up log aggregation (ELK / Loki / CloudWatch)
- [ ] Set up health-check alerting

---

## Directory Structure

```
pharmtrack-microservices/
├── docker-compose.yml          ← Orchestrates all services + infra
├── .env                        ← Shared infra credentials
│
├── gateway/                    ← Django — Auth/Users/Medicines/Vehicles
│   ├── Dockerfile
│   ├── .env
│   ├── manage.py
│   ├── requirements.txt
│   ├── pharmtrack_gateway/
│   │   ├── settings.py
│   │   ├── urls.py
│   │   └── wsgi.py
│   ├── apps/
│   │   ├── authentication/     ← OTP login, JWT issue
│   │   ├── users/              ← User CRUD
│   │   ├── medicines/          ← Medicine inventory
│   │   ├── vehicles/           ← Vehicles, Drivers, Customers
│   │   └── audit/              ← Audit logs + permissions
│   ├── consumers/
│   │   └── delivery_consumer.py ← Subscribes delivery.* to deduct/restore stock
│   ├── management/commands/
│   │   └── run_delivery_consumer.py ← Starts gateway stock consumer
│   └── utils/
│       └── publisher.py        ← RabbitMQ event publisher
│
├── delivery-service/           ← Django — Delivery lifecycle
│   ├── Dockerfile
│   ├── .env
│   ├── manage.py
│   ├── requirements.txt
│   ├── pharmtrack_delivery/
│   ├── apps/deliveries/        ← Models, serializers, views, URLs
│   ├── events/
│   │   └── publisher.py        ← Publishes delivery.* events
│   ├── utils/
│   │   ├── qr_crypto.py        ← AES QR encryption/decryption
│   │   └── stock_client.py     ← Sync HTTP client for gateway stock checks
│   └── management/commands/
│       └── run_consumer.py     ← `python manage.py run_consumer`
│
├── notification-service/       ← Django — In-app notifications
│   ├── Dockerfile
│   ├── .env
│   ├── manage.py
│   ├── requirements.txt
│   ├── pharmtrack_notification/
│   ├── apps/notifications/     ← Models, views, serializers, URLs
│   ├── consumers/
│   │   └── event_consumer.py   ← Subscribes delivery.* + auth events
│   └── management/commands/
│       └── run_consumer.py     ← `python manage.py run_consumer`
│
├── email-service/              ← FastAPI — Async email dispatch
│   ├── Dockerfile
│   ├── .env
│   ├── requirements.txt
│   ├── core/
│   │   └── config.py           ← Pydantic settings
│   └── app/
│       ├── main.py             ← FastAPI app + lifespan consumer start
│       ├── consumers/
│       │   └── email_consumer.py ← Subscribes otp.* + delivery.* events
│       ├── services/
│       │   ├── email_sender.py   ← aiosmtplib async SMTP
│       │   └── template_renderer.py ← Jinja2 renderer
│       └── templates/
│           ├── otp_email.html
│           ├── delivery_assigned.html
│           └── delivery_completed.html
│
└── shared/
    └── events.py               ← Canonical event name constants
```
