> Область применения: `src/app/modules/**/*.py`, `src/app/api/**/*.py`,
> `src/app/kernel/errors.py`.

# Ошибки: RFC 9457

Наружу уходит только `application/problem+json`. Голый `{"detail": "..."}` не
уходит никогда — ни от доменной ошибки, ни от валидации FastAPI, ни от 404
маршрутизатора, ни от необработанного исключения.

- бизнес-код поднимает наследника `AppError` (`NotFound`, `Conflict`,
  `ValidationFailed`, `PermissionDenied`, `Unauthorized`, `RateLimited`,
  `DependencyUnavailable`);
- `HTTPException` запрещён линтером во всём проекте;
- дополнительные члены (`extra`) не вправе перезаписать `type`, `title`,
  `status`, `detail`, `instance`, `request_id`;
- наружу не уходит ни тип исключения, ни его текст: связать ответ с трейсбеком
  можно по `request_id`, он есть и в теле, и в логе.

**Проверяют:** `make check` (ruff `banned-api` на все три написания
`HTTPException`), `tests/test_api_errors.py`, `tests/test_errors.py`,
`tests/test_architecture.py::test_services_never_raise_http_exceptions`.
