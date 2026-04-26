FROM python:3.11-slim

WORKDIR /app

RUN apt-get update && apt-get install -y libpq-dev gcc && rm -rf /var/lib/apt/lists/*

COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt
RUN pip install gunicorn

COPY . .

CMD ["sh", "-c", "python manage.py migrate && python manage.py seed_data && gunicorn config.wsgi:application --bind 0.0.0.0:$PORT"]