FROM python:3.12-slim

# ffmpeg: variant generation (§8-10). fonts-dejavu-core: bold sans-serif
# font for burning captions onto video (backend/services/caption_overlay.py)
# -- DejaVu Sans Bold is a clean, redistributable stand-in for the
# iOS/TikTok-native caption look; Apple's own SF Pro isn't redistributable.
RUN apt-get update && apt-get install -y --no-install-recommends \
    ffmpeg \
    fonts-dejavu-core \
    && rm -rf /var/lib/apt/lists/*

WORKDIR /app

COPY backend/requirements.txt /app/backend/requirements.txt
RUN pip install --no-cache-dir -r /app/backend/requirements.txt

COPY backend /app/backend

ENV PYTHONPATH=/app \
    PYTHONUNBUFFERED=1

EXPOSE 8000

CMD ["uvicorn", "backend.main:app", "--host", "0.0.0.0", "--port", "8000"]
