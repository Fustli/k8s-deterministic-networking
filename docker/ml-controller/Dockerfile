FROM python:3.11-slim

# Minimal image to run the ML controller
WORKDIR /app

# Install runtime system deps for prometheus client / any binary deps (kept minimal)
RUN apt-get update && apt-get install -y --no-install-recommends \
    gcc \
    libpq-dev \
 && rm -rf /var/lib/apt/lists/*

# Copy requirements and install
COPY requirements.txt /app/requirements.txt
RUN pip install --no-cache-dir -r /app/requirements.txt

# Copy app
COPY ml_controller.py /app/ml_controller.py

# Non-root user for security
RUN useradd -m -u 1000 controller
USER controller

# Run the controller
ENTRYPOINT ["python", "/app/ml_controller.py"]
