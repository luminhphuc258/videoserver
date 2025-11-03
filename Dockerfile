# Base Python gọn
FROM python:3.11-slim

# (tùy chọn) giảm noise khi apt
ENV DEBIAN_FRONTEND=noninteractive \
  PYTHONUNBUFFERED=1 \
  OPENCV_LOG_LEVEL=ERROR

WORKDIR /app

# Cài libs tối thiểu cho opencv-python-headless (jpeg/png, glib)
RUN apt-get update && apt-get install -y --no-install-recommends \
  libglib2.0-0 libjpeg62-turbo libpng16-16 ca-certificates \
  && rm -rf /var/lib/apt/lists/*

# Cài deps Python
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

# Copy mã nguồn
COPY . .

# Expose cổng nội bộ (tham khảo)
EXPOSE 8000

# Railway sẽ set $PORT; fallback = 8000 để chạy local
ENV PORT=8000

# Chạy Gunicorn: gthread để stream ổn định, không timeout
CMD gunicorn videoserver:app \
  -k gthread --threads 8 \
  --timeout 0 --keep-alive 75 \
  -b 0.0.0.0:$PORT
