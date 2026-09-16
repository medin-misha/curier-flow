# syntax=docker/dockerfile:1

FROM node:24-alpine AS builder

WORKDIR /build

ARG BACKEND_API_URL=http://localhost:8000
ENV BACKEND_API_URL=$BACKEND_API_URL

COPY package.json package-lock.json ./
RUN --mount=type=cache,target=/root/.npm npm ci

COPY . .
RUN npm run build


FROM node:24-alpine AS runtime

ENV NODE_ENV=production

WORKDIR /app

# Рантайму нужны только production-сборка, её зависимости и публичные файлы.
# Исходники и тесты в финальный образ не копируются.
COPY --from=builder --chown=node:node /build/package.json /build/package-lock.json ./
COPY --from=builder --chown=node:node /build/node_modules ./node_modules
COPY --from=builder --chown=node:node /build/.next ./.next
COPY --from=builder --chown=node:node /build/public ./public

USER node

EXPOSE 3000

CMD ["npm", "run", "start", "--", "--hostname", "0.0.0.0", "--port", "3000"]
