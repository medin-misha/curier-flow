# syntax=docker/dockerfile:1

FROM node:24-alpine AS builder

WORKDIR /build

COPY package.json package-lock.json ./
RUN --mount=type=cache,target=/root/.npm npm ci

COPY . .
RUN npm run build


# Статическая админ-панель не требует Node.js в рантайме. Unprivileged-образ
# слушает непривилегированный порт и запускает nginx не от root.
FROM nginxinc/nginx-unprivileged:1.28-alpine AS runtime

COPY --from=builder --chown=nginx:nginx /build/dist /usr/share/nginx/html
COPY --chown=nginx:nginx nginx.conf /etc/nginx/conf.d/default.conf

EXPOSE 8080
