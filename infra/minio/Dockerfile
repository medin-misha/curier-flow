# Официальные образы MinIO больше недоступны; собираем закреплённые исходники.
# Go должен соответствовать toolchain в go.mod сервера (go1.24.8).
FROM golang:1.24.8-alpine AS build

RUN apk add --no-cache git ca-certificates
# Ограничиваем параллелизм для сборки на небольших серверах.
ENV CGO_ENABLED=0 GOTOOLCHAIN=local GOMAXPROCS=2

WORKDIR /src/minio
RUN git clone --depth 1 --branch RELEASE.2025-10-15T17-29-55Z https://github.com/minio/minio.git .
RUN --mount=type=cache,target=/go/pkg/mod \
    --mount=type=cache,target=/root/.cache/go-build \
    go build -p 2 -tags kqueue -trimpath \
    -ldflags "$(MINIO_RELEASE=RELEASE go run buildscripts/gen-ldflags.go 2025-10-15T17-29-55Z)" \
    -o /out/minio .

# mc нужен существующим healthcheck и одноразовому созданию бакета.
WORKDIR /src/mc
RUN git clone --depth 1 --branch RELEASE.2025-08-13T08-35-41Z https://github.com/minio/mc.git .
RUN --mount=type=cache,target=/go/pkg/mod \
    --mount=type=cache,target=/root/.cache/go-build \
    go build -p 2 -trimpath \
    -ldflags "$(MC_RELEASE=RELEASE go run buildscripts/gen-ldflags.go 2025-08-13T08-35-41Z)" \
    -o /out/mc .

FROM alpine:3.22
RUN apk add --no-cache ca-certificates
COPY --from=build /out/minio /out/mc /usr/bin/
COPY --from=build /src/minio/dockerscripts/docker-entrypoint.sh /usr/bin/docker-entrypoint.sh
COPY --from=build /src/minio/LICENSE /licenses/minio-LICENSE
COPY --from=build /src/mc/LICENSE /licenses/mc-LICENSE
EXPOSE 9000 9001
ENTRYPOINT ["/usr/bin/docker-entrypoint.sh"]
CMD ["minio"]
