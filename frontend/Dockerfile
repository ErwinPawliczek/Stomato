# Web image (spec P3-03): build the Vite app, serve dist/ with nginx, and proxy
# /api to the api service (compose service name `api`; the Helm chart mounts a
# ConfigMap that overrides this file with the chart's api Service name).
# Build context is the repo root (see deploy/compose.yaml and
# .github/workflows/release.yml), so frontend paths are prefixed below.
FROM node:22.13.0-alpine AS build
WORKDIR /app
COPY frontend/package.json frontend/package-lock.json ./
RUN npm ci
COPY frontend/ ./
RUN npm run build

FROM nginx:1.27.3-alpine
COPY --from=build /app/dist /usr/share/nginx/html
RUN rm /etc/nginx/conf.d/default.conf
# Static SPA + API proxy: cache hashed assets, never cache index.html.
RUN <<'EOF' >> /etc/nginx/conf.d/default.conf
server {
  listen 80;
  root /usr/share/nginx/html;
  index index.html;
  location /api/ {
    proxy_pass http://api:8000;
    proxy_http_version 1.1;
    proxy_set_header Host $host;
    proxy_set_header X-Real-IP $remote_addr;
    proxy_set_header X-Forwarded-For $proxy_add_x_forwarded_for;
    proxy_set_header X-Forwarded-Proto $scheme;
    # Long-lived Server-Sent Events (solve-job progress): no buffering, no
    # short read timeout.
    proxy_buffering off;
    proxy_read_timeout 3600s;
  }
  location /assets/ {
    expires 1y;
    add_header Cache-Control "public, immutable";
  }
  location / {
    try_files $uri $uri/ /index.html;
  }
}
EOF
EXPOSE 80
