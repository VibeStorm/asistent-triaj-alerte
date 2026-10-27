# NETESTAT: acest Dockerfile nu a fost construit sau rulat de autor (fără Docker pe calculator).
FROM python:3.12-slim

ENV PYTHONDONTWRITEBYTECODE=1 PYTHONUNBUFFERED=1 ASISTENT_HOST=0.0.0.0

RUN useradd --create-home appuser
WORKDIR /app

COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

COPY asistent_triaj ./asistent_triaj
RUN chown -R appuser:appuser /app
USER appuser

EXPOSE 5000

# generează datele sintetice, apoi pornește serverul (Flask de dezvoltare, nu server de producție)
CMD ["sh", "-c", "python -m asistent_triaj.generate_data && python -m asistent_triaj.app"]
