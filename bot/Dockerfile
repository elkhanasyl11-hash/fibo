# Fibo Telegram bot (long polling). No database, no ML: it only calls the backend over HTTP.
FROM python:3.11-slim

ENV PYTHONDONTWRITEBYTECODE=1 PYTHONUNBUFFERED=1

WORKDIR /app
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

ARG UID=1000
RUN useradd --create-home --uid ${UID} fibo
COPY --chown=fibo . .
USER fibo

CMD ["python", "-m", "bot.main"]
