"""Выпуск, проверка и обновление JWT.

Модуля авторизации в шаблоне нет: здесь только примитивы, на которых он потом
собирается. Кто такой пользователь, где хранятся его пароли и как выглядит
ручка входа — решает сервис; ядро отвечает лишь за то, чтобы подписанная
строка нельзя было подделать, переиспользовать не по назначению или предъявить
после истечения срока.

Два типа токенов и почему их нельзя смешивать
---------------------------------------------
Access живёт минуты и предъявляется каждому запросу — он утекает первым: из
логов прокси, из истории браузера, из отчёта об ошибке. Refresh живёт недели,
но ходит только в одну ручку обновления. Если проверка не различает типы, то
утёкший access становится вечным (им можно выпустить новую пару), а смысл
короткого срока жизни пропадает. Поэтому тип вшит в полезную нагрузку
(`typ`), и `decode_token` требует назвать ожидаемый тип явно.

Симметричная подпись (HS256) годится, пока токены выпускает и проверяет один
сервис: секрет знают обе стороны, потому что это одна сторона. Как только
токены начнёт проверять чужой сервис, алгоритм меняется на асимметричный
(RS256/EdDSA) — иначе секрет придётся раздать всем проверяющим, а вместе с ним
и право выпускать токены.
"""

from dataclasses import dataclass
from datetime import UTC, datetime, timedelta
from enum import StrEnum
from typing import Any, Final, Self
from uuid import UUID, uuid4

import jwt
from pydantic import Field, SecretStr, model_validator
from pydantic_settings import BaseSettings, SettingsConfigDict

from app.kernel.config import settings
from app.kernel.errors import Unauthorized

#: Значение секрета из `.env.example`. Оно обязано быть заметным и обязано
#: ронять прод: подписанный им токен подделывает кто угодно, у кого есть
#: репозиторий шаблона.
DEFAULT_SECRET: Final = "change-me-in-production"  # noqa: S105  # он и должен быть здесь

#: Обязательные члены полезной нагрузки. Токен без любого из них — не наш:
#: без `exp` он вечен, без `typ` его нельзя отличить от refresh, без `sub`
#: непонятно, кто действует, без `jti` две выдачи подряд неразличимы.
_REQUIRED_CLAIMS: Final = ("exp", "iat", "sub", "jti", "typ")


class TokenType(StrEnum):
    """Назначение токена. Значение уезжает в полезную нагрузку как `typ`."""

    ACCESS = "access"
    REFRESH = "refresh"


class JwtSettings(BaseSettings):
    """Настройки подписи и сроков жизни токенов."""

    model_config = SettingsConfigDict(
        env_prefix="jwt_",
        env_file=".env",
        env_file_encoding="utf-8",
        extra="ignore",
    )

    #: `SecretStr`, чтобы секрет не всплыл в repr настроек — а он попадает и в
    #: сообщения об ошибках валидации, и в отладочный вывод.
    secret: SecretStr = SecretStr(DEFAULT_SECRET)

    algorithm: str = "HS256"

    #: Срок жизни access в секундах: минуты. Отозвать выданный токен нельзя,
    #: поэтому «сколько живёт access» — это и есть окно, в течение которого
    #: уволенный сотрудник или утёкший токен ещё работают.
    access_ttl: int = Field(default=900, ge=1)

    #: Срок жизни refresh в секундах: недели. Это интервал, после которого
    #: пользователь обязан войти заново.
    refresh_ttl: int = Field(default=1_209_600, ge=1)

    @model_validator(mode="after")
    def _forbid_default_secret_in_production(self) -> Self:
        """Не дать процессу подняться в проде с секретом из репозитория.

        Проверка живёт в настройках, а не в точке входа: тогда она срабатывает
        для любого процесса (api, воркер, миграции) и до первого обслуженного
        запроса. Ошибка конфигурации, замеченная на старте, стоит одного
        падения выкатки; замеченная в бою — всех выданных токенов сразу.
        """
        if settings.app_env == "prod" and self.secret.get_secret_value() == DEFAULT_SECRET:
            raise ValueError(
                "JWT_SECRET is still the template default: anyone with the repository "
                "can forge tokens. Set a random secret from your secret store."
            )
        return self


#: Единственный экземпляр настроек процесса.
jwt_settings = JwtSettings()


@dataclass(frozen=True, slots=True)
class TokenClaims:
    """Разобранная и проверенная полезная нагрузка токена."""

    subject: UUID
    token_type: TokenType
    issued_at: datetime
    expires_at: datetime

    #: Идентификатор выдачи. Пригодится списку отзыва: отзывать по `sub`
    #: значит выкидывать все сессии пользователя сразу.
    token_id: UUID

    #: Полная нагрузка, включая произвольные члены вызывающего (роли, арендатор).
    #: Ядро о них ничего не знает и не проверяет их.
    payload: dict[str, Any]


@dataclass(frozen=True, slots=True)
class TokenPair:
    """Пара токенов и срок жизни access в секундах — то, что уходит клиенту."""

    access_token: str
    refresh_token: str
    expires_in: int


def issue_tokens(
    subject: UUID,
    *,
    settings: JwtSettings,
    claims: dict[str, Any] | None = None,
) -> TokenPair:
    """Выпустить пару токенов для пользователя.

    Принимает идентификатор пользователя, настройки подписи и необязательные
    дополнительные члены нагрузки, возвращает пару. Кидает `ValueError`, если
    дополнительные члены пытаются переопределить служебные.

    Дополнительные члены попадают только в access: refresh предъявляется
    единственной ручке обновления, и роли в нём успели бы устареть — а
    доверять устаревшим ролям хуже, чем сходить за ними в базу.
    """
    now = datetime.now(tz=UTC)
    return TokenPair(
        access_token=_encode(
            subject,
            TokenType.ACCESS,
            issued_at=now,
            ttl=settings.access_ttl,
            settings=settings,
            claims=claims,
        ),
        refresh_token=_encode(
            subject,
            TokenType.REFRESH,
            issued_at=now,
            ttl=settings.refresh_ttl,
            settings=settings,
            claims=None,
        ),
        expires_in=settings.access_ttl,
    )


def decode_token(token: str, *, expected: TokenType, settings: JwtSettings) -> TokenClaims:
    """Проверить подпись, срок и назначение токена.

    Принимает строку токена, ожидаемое назначение и настройки, возвращает
    разобранные утверждения. Кидает `Unauthorized` на любую негодность:
    испорченную подпись, истёкший срок, отсутствующий член нагрузки, чужой тип
    токена. Причина уточняется полем `reason` — по нему клиенту видно, стоит
    ли обновлять токен или нужно входить заново.

    Список алгоритмов задаётся явно и состоит из одного значения. Это не
    формальность: проверка «алгоритм из заголовка токена» — известная дыра,
    через которую подпись снимают, объявив `alg: none`.
    """
    try:
        payload: dict[str, Any] = jwt.decode(
            token,
            settings.secret.get_secret_value(),
            algorithms=[settings.algorithm],
            options={"require": list(_REQUIRED_CLAIMS)},
        )
    except jwt.ExpiredSignatureError as error:
        raise Unauthorized("Token has expired", reason="expired") from error
    except jwt.InvalidTokenError as error:
        raise Unauthorized("Token is not valid", reason="malformed") from error

    if payload["typ"] != expected.value:
        raise Unauthorized(
            f"Expected a {expected.value} token, got {payload['typ']}",
            reason="wrong-token-type",
        )

    try:
        subject = UUID(payload["sub"])
        token_id = UUID(payload["jti"])
    except (AttributeError, TypeError, ValueError) as error:
        raise Unauthorized("Token subject is not a valid identifier", reason="malformed") from error

    return TokenClaims(
        subject=subject,
        token_type=expected,
        issued_at=datetime.fromtimestamp(payload["iat"], tz=UTC),
        expires_at=datetime.fromtimestamp(payload["exp"], tz=UTC),
        token_id=token_id,
        payload=payload,
    )


def refresh_tokens(refresh_token: str, *, settings: JwtSettings) -> TokenPair:
    """Обменять refresh-токен на новую пару.

    Принимает refresh-токен и настройки, возвращает новую пару. Кидает
    `Unauthorized`, если токен негоден или это не refresh.

    Обновляются оба токена, а не только access: иначе refresh пришлось бы
    выпускать вечным, и однажды утёкший давал бы доступ навсегда. Пара
    выдаётся новая целиком, поэтому у сервиса появляется возможность заметить
    повторное использование старого refresh — но список отзыва здесь не
    заводится: ему нужно хранилище, а значит и решение о том, чьё оно.
    """
    claims = decode_token(refresh_token, expected=TokenType.REFRESH, settings=settings)
    return issue_tokens(claims.subject, settings=settings)


def _encode(
    subject: UUID,
    token_type: TokenType,
    *,
    issued_at: datetime,
    ttl: int,
    settings: JwtSettings,
    claims: dict[str, Any] | None,
) -> str:
    """Собрать и подписать один токен.

    Служебные члены ставятся последними: дополнительные члены вызывающего не
    должны молча подменить `sub` или `exp`, а тихая подмена страшнее отказа.
    """
    payload: dict[str, Any] = dict(claims or {})
    reserved = sorted(set(payload) & set(_REQUIRED_CLAIMS))
    if reserved:
        raise ValueError(f"Reserved JWT claims cannot be overridden: {', '.join(reserved)}")

    payload.update(
        {
            # `sub` строкой: PyJWT требует от него строку, а UUID сериализуется
            # в JSON только вручную.
            "sub": str(subject),
            "typ": token_type.value,
            "jti": str(uuid4()),
            "iat": issued_at,
            "exp": issued_at + timedelta(seconds=ttl),
        }
    )
    return jwt.encode(payload, settings.secret.get_secret_value(), algorithm=settings.algorithm)
