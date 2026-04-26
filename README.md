# Playto Payout Engine

A production-grade payout engine built for the Playto Founding Engineer Challenge.
Handles merchant ledgers, payout requests, concurrency safety, idempotency, and async processing.

=======
A production-grade payout engine built for the Playto Founding Engineer Challenge 2026.
Handles merchant ledgers, payout requests, concurrency safety, idempotency, and async processing.

## Live Deployment

| Service | URL |
|---------|-----|
| Frontend | https://playto-payout-engine-alpha.vercel.app |
| Backend API |  https://playto-payout-engine-0aut.onrender.com/api/v1/merchants/ |
| API Base | https://playto-payout-engine-0aut.onrender.com/api/v1/merchants/ |

> Note: Backend is on Render free tier. First request may take 50 seconds to wake up.

---

## Tech Stack

- **Backend:** Django + Django REST Framework
- **Database:** PostgreSQL (all money in paise as BigIntegerField)
- **Queue:** Celery + Redis
- **Frontend:** React + Vite + Tailwind CSS

---

## Local Setup (Without Docker)
=======
| Layer | Technology |
|-------|-----------|
| Backend | Django + Django REST Framework |
| Database | PostgreSQL (all money in paise as BigIntegerField) |
| Queue | Celery + Redis |
| Frontend | React + Vite + Tailwind CSS |
| Deployment | Render (backend) + Vercel (frontend) |

---

## Core Features

- Merchant ledger with immutable credit/debit entries
- Balance always derived from DB aggregation — never stored as a column
- Payout request API with Idempotency-Key header support
- Held funds on pending/processing payouts
- Celery background worker: 70% success, 20% failure, 10% stuck
- Payout state machine: pending → processing → completed/failed
- Retry logic with exponential backoff (max 3 attempts)
- Concurrency-safe: select_for_update prevents overdraw
- React dashboard with live status polling every 5 seconds

---

## Local Setup

### Prerequisites
- Python 3.11+
- PostgreSQL 17
- Redis
- Node.js 18+

### 1. Clone and create virtual environment

```bash
git clone <your-repo-url>
cd playto-payout-engine

python -m venv venv
# Windows:
.\venv\Scripts\Activate.ps1
=======
### 1. Clone the repository

```bash
git clone https://github.com/KaustubhP234/playto-payout-engine.git
cd playto-payout-engine
```

### 2. Create virtual environment

```bash
python -m venv venv

# Windows:
.\venv\Scripts\Activate.ps1

>>>>>>> 8953c7c (docs: update README with live deployment URLs)
# Mac/Linux:
source venv/bin/activate
```

### 2. Install backend dependencies
=======
### 3. Install backend dependencies

```bash
cd backend
pip install -r requirements.txt
```

### 3. Configure environment

```bash
cp .env.example .env
# Edit .env with your PostgreSQL credentials
```

### 4. Create database and run migrations
=======
### 4. Configure environment

```bash
cp .env.example .env
# Edit .env with your PostgreSQL and Redis credentials
```

### 5. Create database and run migrations

```bash
psql -U postgres -c "CREATE DATABASE playto_db;"
python manage.py migrate
```

### 5. Seed merchants
=======
### 6. Seed merchants

```bash
python manage.py seed_data
```

### 6. Start Django
=======
### 7. Start Django

```bash
python manage.py runserver
```

### 7. Start Celery worker (new terminal)

```bash
celery -A config worker --loglevel=info
```

### 8. Start Celery beat (new terminal)
=======
### 8. Start Celery worker (new terminal)

```bash
celery -A config worker --loglevel=info --pool=solo
```

### 9. Start Celery beat (new terminal)

```bash
celery -A config beat --loglevel=info --scheduler django_celery_beat.schedulers:DatabaseScheduler
```

### 9. Start frontend (new terminal)
=======
### 10. Start frontend (new terminal)

```bash
cd frontend
npm install
npm run dev
```

Open **http://localhost:5173**

---

## Docker Setup

```bash
docker-compose up --build
```

Open **http://localhost:5173** (frontend must be run separately via `npm run dev`)

=======
---

## API Reference

| Method | Endpoint | Description |
|--------|----------|-------------|
| GET | `/api/v1/merchants/` | List all merchants |
| GET | `/api/v1/merchants/:id/` | Merchant detail |
| GET | `/api/v1/merchants/:id/balance/` | Live balance |
| GET | `/api/v1/merchants/:id/ledger/` | Ledger entries |
| GET | `/api/v1/merchants/:id/payouts/` | Payout history |
| POST | `/api/v1/merchants/:id/payouts/` | Create payout |
| GET | `/api/v1/merchants/:id/payouts/:pid/` | Payout detail |

<<<<<<< HEAD
### Create Payout
=======
### Create Payout Request
POST /api/v1/merchants/:id/payouts/
Headers:
Idempotency-Key: <uuid>
Content-Type: application/json
Body:
{
"amount_paise": 50000,
"bank_account_id": "HDFC_XXXX_0042"
}

### Response

```json
{
  "id": "uuid",
  "merchant": "uuid",
  "amount_paise": 50000,
  "bank_account_id": "HDFC_XXXX_0042",
  "status": "pending",
  "idempotency_key": "uuid",
  "created_at": "2026-04-26T00:00:00Z",
  "updated_at": "2026-04-26T00:00:00Z"
}
```

---

## Running Tests

```bash
cd backend
pytest payouts/tests.py -v
```

**13 tests covering:**
- Idempotency (4 tests) — same key returns same payout, no duplicates, key scoped per merchant
- Concurrency (2 tests) — overdraw prevention, balance never goes negative
- State machine (7 tests) — valid and invalid transitions

---

## Seed Data

```bash
python manage.py seed_data
```

Creates 3 merchants with realistic credit history:

| Merchant | Balance |
|----------|---------|
| Arjun Mehta Designs | ₹7,000.00 |
| Priya Software Exports | ₹17,250.00 |
| Rohan Creative Studio | ₹5,480.00 |

To reset and re-seed:
```bash
python manage.py seed_data --reset
```

---

## Environment Variables

```env
SECRET_KEY=your-secret-key
DEBUG=False
DATABASE_URL=postgres://USER:PASSWORD@HOST:PORT/DB_NAME
REDIS_URL=redis://localhost:6379/0
ALLOWED_HOSTS=localhost,127.0.0.1
```

---

## Project Structure
playto-payout-engine/
├── backend/
│   ├── config/          # Django settings, URLs, Celery
│   ├── payouts/         # Models, views, serializers, tasks, tests
│   ├── manage.py
│   ├── requirements.txt
│   ├── Dockerfile
│   └── .env.example
├── frontend/
│   └── src/
│       ├── components/  # Sidebar, BalanceCards, PayoutForm, PayoutTable, LedgerTable
│       ├── api.js       # API client
│       └── App.jsx      # Main dashboard
├── docker-compose.yml
├── README.md
└── EXPLAINER.md

