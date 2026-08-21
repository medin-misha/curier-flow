## Шаг 9. Настройки

Если у модуля есть лимиты, TTL или расписания — класс настроек живёт рядом с
владельцем, в `services.py`:

```python
class NotesSettings(BaseSettings):
    """Лимиты и расписания модуля notes."""

    model_config = SettingsConfigDict(
        env_prefix="notes_",
        env_file=".env",
        env_file_encoding="utf-8",
        extra="ignore",
    )

    retention_days: int = Field(default=90, ge=1)


#: Единственный экземпляр настроек процесса.
notes_settings = NotesSettings()
```

- `os.getenv` и `os.environ` запрещены линтером: конфигурация читается только
  через pydantic-settings;
- **каждая переменная дописывается в `.env.example`** — в свою секцию, с
  комментарием, зачем она и чем грозит неудачное значение. Дефолт в коде обязан
  совпадать со значением в файле;
- класс перечисляется в манифесте (`settings=NotesSettings`).
