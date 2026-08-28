## Команды

```bash
uv run pytest tests/test_storage.py -v      # тесты модуля (нужен docker)
make -C ../../infra migrate                 # таблица files в окружении стека
uv run alembic check                        # схема совпадает с моделями

# Полный цикл руками (стек поднят из корня через `make -C infra up`):
curl -s localhost:8000/files/upload-url -H 'content-type: application/json' \
  -d '{"original_name":"a.png","content_type":"image/png","size":4}'
curl -i -X PUT "<upload_url>" -H 'content-type: image/png' --data-binary @a.png
curl -s -X POST localhost:8000/files/<id>/confirm -H 'content-type: application/json' \
  -d '{"etag":"<etag из заголовка ответа PUT>"}'
curl -s localhost:8000/files/<id>           # download_url открывается в браузере
```
