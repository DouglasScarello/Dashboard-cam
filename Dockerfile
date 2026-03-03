# Dockerfile para o Motor de Inteligência (Olho de Deus)
FROM python:3.11-slim

# Evitar prompts durante a instalação
ENV DEBIAN_FRONTEND=noninteractive

# Instalar dependências do sistema (OpenCV, PostgreSQL client, etc)
RUN apt-get update && apt-get install -y --no-install-recommends \
    build-essential \
    libpq-dev \
    libgl1-mesa-glx \
    libglib2.0-0 \
    libsm6 \
    libxext6 \
    libxrender-dev \
    curl \
    git \
    && rm -rf /var/lib/apt/lists/*

WORKDIR /app

# Instalar dependências Python
# Nota: Como o sistema usa poetry e scripts espalhados, vamos copiar o essencial
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

# Copiar os módulos do projeto
COPY intelligence/ intelligence/
COPY olho_de_deus/ olho_de_deus/

# Configurar variáveis de ambiente
ENV PYTHONPATH=/app
ENV DB_HOST=db
ENV DB_PORT=5432
ENV DB_NAME=intelligence
ENV DB_USER=ghost
ENV DB_PASS=protocol

# Comando padrão (pode ser sobrescrito pelo docker-compose)
CMD ["python", "olho_de_deus/main.py"]
