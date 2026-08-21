## Команды

```bash
uv run pytest tests/test_health.py -v          # тесты модуля
curl -s localhost:8000/health/live             # 200 всегда, пока процесс жив
curl -si localhost:8000/health/ready | head -1 # 200 или 503
curl -s localhost:8000/health/info             # revision = null, если БД недоступна
docker compose ps                              # api healthy = /health/live отвечает
```
