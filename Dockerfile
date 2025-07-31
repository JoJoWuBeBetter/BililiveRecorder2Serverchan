# Use a slim Python image for smaller size and faster builds
FROM python:3.9-slim-buster

# Set environment variables for the container
ENV SERVERCHAN_SEND_KEY=""
ENV TENCENTCLOUD_SECRET_ID=""
ENV TENCENTCLOUD_SECRET_KEY=""
ENV TENCENTCLOUD_COS_BUCKET=""
ENV TENCENTCLOUD_COS_REGION=""
ENV PYTHONUNBUFFERED=1
ENV GUNICORN_WORKERS=2
ENV GUNICORN_BIND_ADDRESS="0.0.0.0:8000"

# Set the working directory inside the container
WORKDIR /app

# Copy requirements.txt first to leverage Docker layer caching
COPY requirements.txt .

# Install Python dependencies
RUN pip install --no-cache-dir -r requirements.txt

# Copy the rest of the application code into the container
COPY . .

# Expose the port FastAPI will run on
EXPOSE 8000

# Command to run the application using Gunicorn with Uvicorn workers
# Explicitly call /bin/sh -c to allow environment variable expansion
CMD ["/bin/sh", "-c", "gunicorn main:app --workers $GUNICORN_WORKERS --worker-class uvicorn.workers.UvicornWorker --bind $GUNICORN_BIND_ADDRESS"]