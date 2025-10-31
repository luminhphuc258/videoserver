# Use a lightweight Python base image
FROM python:3.11-slim

# Set working directory
WORKDIR /app

# Copy dependency list
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

# Copy your server code
COPY . .

# Expose Flask port
EXPOSE 8000

# Start the Flask app with Gunicorn
CMD ["gunicorn", "-b", "0.0.0.0:8000", "videoserver:app"]
