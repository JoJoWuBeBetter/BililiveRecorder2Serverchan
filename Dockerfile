# Use a slim Python image for smaller size and faster builds
FROM python:3.9-slim-buster

# Set environment variables for the container
# This defines the variable but doesn't set its value by default.
# The actual value for SERVERCHAN_SENDKEY should be passed during `docker run` using the -e flag.
ENV SERVERCHAN_SENDKEY=""
# Ensures that Python output is sent straight to the terminal without buffering
ENV PYTHONUNBUFFERED=1
# Number of Gunicorn workers (adjust based on CPU cores)
ENV GUNICORN_WORKERS=2
# Address and port Gunicorn will listen on
ENV GUNICORN_BIND_ADDRESS="0.0.0.0:8000"

# Set the working directory inside the container
WORKDIR /app

# Copy requirements.txt first to leverage Docker layer caching
COPY requirements.txt .

# Install Python dependencies
# --no-cache-dir: Don't store cache in Docker image (reduces image size)
# -r: Install from requirements file
RUN pip install --no-cache-dir -r requirements.txt

# Copy the rest of the application code into the container
COPY . .

# Expose the port FastAPI will run on
EXPOSE 8000

# Command to run the application using Gunicorn with Uvicorn workers
# `main:app` refers to the 'app' object inside the 'main.py' file.
# --workers: Number of worker processes. Recommended (2 * CPU_CORES) + 1, or simply 2-4 for common use cases.
# --worker-class uvicorn.workers.UvicornWorker: Specifies Uvicorn as the ASGI worker class.
# --bind: The address and port to bind to. "0.0.0.0:8000" means accessible from anywhere on port 8000.
CMD ["gunicorn", "main:app", \
     "--workers", "${GUNICORN_WORKERS}", \
     "--worker-class", "uvicorn.workers.UvicornWorker", \
     "--bind", "${GUNICORN_BIND_ADDRESS}"]
