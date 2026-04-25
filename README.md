# Playto Payout Engine

A production-grade payout engine built for the Playto Founding Engineer Challenge.
Handles merchant ledgers, payout requests, concurrency safety, idempotency, and async processing.

---

## Tech Stack

- **Backend:** Django + Django REST Framework
- **Database:** PostgreSQL (all money in paise as BigIntegerField)
- **Queue:** Celery + Redis
- **Frontend:** React + Vite + Tailwind CSS

---

## Local Setup (Without Docker)

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
# Mac/Linux:
source venv/bin/activate
```

### 2. Install backend dependencies

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

```bash
psql -U postgres -c "CREATE DATABASE playto_db;"
python manage.py migrate
```

### 5. Seed merchants

```bash
python manage.py seed_data
```

### 6. Start Django

```bash
python manage.py runserver
```

### 7. Start Celery worker (new terminal)

```bash
celery -A config worker --loglevel=info
```

### 8. Start Celery beat (new terminal)

```bash
celery -A config beat --loglevel=info --scheduler django_celery_beat.schedulers:DatabaseScheduler
```

### 9. Start frontend (new terminal)

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

### Create Payout