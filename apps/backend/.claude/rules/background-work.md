---
paths:
  - "src/app/modules/**/tasks.py"
  - "src/app/modules/**/consumers.py"
  - "src/app/worker.py"
  - "src/app/platform/taskiq.py"
  - "src/app/platform/rabbitmq.py"
---

# TaskIQ против RabbitMQ

|  | TaskIQ (`platform/taskiq.py`) | RabbitMQ напрямую (`platform/rabbitmq.py`) |
| --- | --- | --- |
| Для чего | наша собственная работа | обмен с внешними сервисами |
| Примеры | релей outbox, уборка таблиц, отложенная отправка | сообщение из чужого сервиса, сообщение в чужой сервис |
| Как объявляется | корутина + `@schedule(...)`, перечислена в `Module.tasks` | `TopologyDecl` + `ConsumerDecl` в манифесте |
| Формат | наш, вправе менять вместе с кодом | чужой контракт, менять нельзя |

Общее правило: **и то и другое живёт только в процессе `worker.py`.** В uvicorn
не поднимается ни консьюмер, ни шедулер, ни релей. Фоновая работа в веб-процессе
умирает при перекатке и размножается вместе с числом воркеров uvicorn:
периодическая задача начинает выполняться N раз.

`kiq()` из HTTP-ручки — обращение к брокеру, и внутри транзакции ему не место.
Работа, которую нельзя потерять, ставится строкой в таблице (статус, outbox), а
не постановкой задачи в брокер.

**Проверяют:** `tests/test_process_isolation.py::test_http_entrypoint_does_not_import_platform`,
`::test_lifespan_opens_no_connections`, `tests/test_taskiq.py`,
`tests/test_worker.py`.

Выбор механизма под конкретный эффект — скилл `background-effect`.
