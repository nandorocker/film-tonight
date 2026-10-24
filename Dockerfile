FROM node:24-bookworm-slim
RUN apt-get update && apt-get install -y --no-install-recommends python3 ca-certificates tzdata && rm -rf /var/lib/apt/lists/*
WORKDIR /app
COPY package.json package-lock.json ./
RUN npm ci
COPY . .
RUN mkdir -p data .wrangler && chown -R node:node /app
USER node
CMD ["python3", "tools/local.py"]
