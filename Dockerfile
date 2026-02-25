FROM python:3.11-slim

ENV PYTHONDONTWRITEBYTECODE=1
ENV PYTHONUNBUFFERED=1

WORKDIR /app

RUN apt-get update && apt-get install -y --no-install-recommends \
    build-essential libjpeg-dev zlib1g-dev \
  && rm -rf /var/lib/apt/lists/*

COPY requirements.txt ./
RUN pip install --upgrade pip && pip install -r requirements.txt

COPY . .

RUN mkdir -p media/user_images media/admin_profiles media/admin_ids media/found_pets media/lost_pets

EXPOSE 5000

CMD ["gunicorn","-k","eventlet","-w","1","app:app","-b","0.0.0.0:5000"]
