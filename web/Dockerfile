FROM node:20-alpine AS build

WORKDIR /app
COPY web/ /app/
ENV VITE_BASE_PATH=/poke-battles/
RUN npm ci --no-audit --no-fund && \
    npm run build

FROM nginx:1.27-alpine

COPY --from=build /app/dist/ /usr/share/nginx/html/poke-battles/
COPY web/nginx.conf /etc/nginx/conf.d/default.conf

EXPOSE 80

HEALTHCHECK --interval=30s --timeout=3s --retries=3 \
    CMD wget -qO- http://localhost/poke-battles/ >/dev/null || exit 1
