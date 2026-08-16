"""Базовые схемы Pydantic для запросов и ответов.

Разделены намеренно: у запроса и ответа разные требования к валидации, и
общий базовый класс их бы смешал.
"""

from pydantic import BaseModel, ConfigDict


class BaseRequest(BaseModel):
    """База для входящих схем.

    `extra="forbid"` — чтобы опечатка в имени поля возвращала 422, а не
    молча игнорировалась: клиент, отправивший `titel` вместо `title`, должен
    узнать об этом сразу, а не по отсутствию эффекта.
    """

    model_config = ConfigDict(extra="forbid")


class BaseResponse(BaseModel):
    """База для исходящих схем.

    `from_attributes=True` позволяет собирать ответ прямо из ORM-объекта через
    `model_validate`, без ручного перекладывания полей.
    """

    model_config = ConfigDict(from_attributes=True)
