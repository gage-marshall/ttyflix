FROM python:3.12-slim

# Install ffmpeg from the distribution package manager.
# This replaces the bundled ffmpeg.exe used on Windows.
RUN apt-get update \
 && apt-get install -y --no-install-recommends ffmpeg \
 && rm -rf /var/lib/apt/lists/*

WORKDIR /app

# Install Python dependencies first so Docker can cache this layer.
COPY requirements.txt ./
RUN pip install --no-cache-dir -r requirements.txt

# Copy application source.
COPY ansi_render.py web_server.py telnet_server.py ssh_server.py convert.py serve.py ./
COPY server/ ./server/

# www/, videos/, output/, and config.toml are bind-mounted at runtime
# (see docker-compose.yml) so they stay outside the image and are easy
# to edit without rebuilding.

# Telnet server + HTTP landing page
EXPOSE 23 8080

CMD ["python", "serve.py"]
