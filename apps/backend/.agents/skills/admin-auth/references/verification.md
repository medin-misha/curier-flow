# Проверки auth

## Проверяемые сценарии

Основные тесты — `tests/test_admin.py` и `tests/test_authentication.py`. При
изменении механизма сохраняй проверки:

- одинакового `401` и dummy verify;
- rehash и отсутствия plaintext secrets;
- missing/disabled/version-mismatched Admin;
- rotation, reuse family revoke и concurrent refresh;
- password/deactivation invalidation;
- self-lockout и встречной деактивации;
- concurrent bootstrap, no-op и missing credentials;
- cookie flags, no-store и production policy;
- keyset index, migration и cleanup.
