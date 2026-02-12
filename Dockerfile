FROM python:3.11-slim

# Security: Run as non-root user
RUN useradd -m -u 1000 appuser

WORKDIR /app

# Install system dependencies
RUN apt-get update && apt-get install -y \
    gcc \
    postgresql-client \
    && rm -rf /var/lib/apt/lists/*

# Copy requirements
COPY requirements.txt .

# Install Python dependencies
RUN pip install --no-cache-dir -r requirements.txt

# Copy project
COPY SemirDashboard/ /app/

# Set ownership
RUN chown -R appuser:appuser /app

# Switch to non-root user
USER appuser

# Collect static files
RUN python manage.py collectstatic --noinput

EXPOSE 8000

CMD ["gunicorn", "SemirDashboard.wsgi:application", "--bind", "0.0.0.0:8000", "--workers", "3", "--timeout", "120"]