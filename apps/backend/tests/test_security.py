"""Примитивы безопасности: пароли на argon2 и подпись JWT."""

from datetime import UTC, datetime, timedelta
from typing import Any, Final
from uuid import UUID, uuid4

import jwt
import pytest
from argon2 import PasswordHasher
from pydantic import SecretStr, ValidationError

from app.kernel.config import settings
from app.kernel.errors import Unauthorized
from app.kernel.security.passwords import (
    hash_password,
    password_needs_rehash,
    verify_password,
)
from app.kernel.security.tokens import (
    DEFAULT_SECRET,
    JwtSettings,
    TokenType,
    decode_token,
    issue_tokens,
    refresh_tokens,
)

#: Дешёвые параметры: боевые считаются десятки миллисекунд, а проверяется здесь
#: поведение функций, а не стойкость библиотеки.
CHEAP: Final = PasswordHasher(time_cost=1, memory_cost=8, parallelism=1)

#: Подпись тестов. Не глобальный `jwt_settings`: его секрет короче 32 байт, и
#: PyJWT предупреждает о слабом ключе, а предупреждения в прогоне — ошибки.
JWT: Final = JwtSettings(secret=SecretStr("0123456789abcdef0123456789abcdef"))

ACTOR: Final = UUID(int=42)


def test_the_hash_hides_the_password() -> None:
    hashed = hash_password("correct horse", hasher=CHEAP)

    assert "correct horse" not in hashed
    assert hashed.startswith("$argon2id$")


def test_two_hashes_of_one_password_differ() -> None:
    """Соль генерирует библиотека: одинаковые пароли не должны совпадать в базе."""
    first = hash_password("correct horse", hasher=CHEAP)
    second = hash_password("correct horse", hasher=CHEAP)

    assert first != second


def test_the_right_password_verifies() -> None:
    hashed = hash_password("correct horse", hasher=CHEAP)

    assert verify_password("correct horse", hashed, hasher=CHEAP)


@pytest.mark.parametrize("hashed", ["$argon2id$broken", "", "not a hash at all"])
def test_a_broken_hash_is_not_an_exception(hashed: str) -> None:
    """Мусор в колонке пароля означает «вход не состоялся», а не 500."""
    assert not verify_password("correct horse", hashed, hasher=CHEAP)


def test_the_wrong_password_does_not_verify() -> None:
    hashed = hash_password("correct horse", hasher=CHEAP)

    assert not verify_password("wrong horse", hashed, hasher=CHEAP)


def test_a_hash_from_weaker_parameters_needs_a_rehash() -> None:
    """Поднятая стойкость обязана доезжать до старых учётных записей."""
    weaker = PasswordHasher(time_cost=1, memory_cost=8, parallelism=1)
    stronger = PasswordHasher(time_cost=2, memory_cost=16, parallelism=1)

    hashed = hash_password("correct horse", hasher=weaker)

    assert password_needs_rehash(hashed, hasher=stronger)
    assert not password_needs_rehash(hashed, hasher=weaker)


def test_an_access_token_carries_its_subject() -> None:
    pair = issue_tokens(ACTOR, settings=JWT)

    claims = decode_token(pair.access_token, expected=TokenType.ACCESS, settings=JWT)

    assert claims.subject == ACTOR
    assert claims.token_type is TokenType.ACCESS
    assert pair.expires_in == JWT.access_ttl
    assert claims.expires_at - claims.issued_at == timedelta(seconds=JWT.access_ttl)


def test_extra_claims_travel_in_the_access_token_only() -> None:
    pair = issue_tokens(ACTOR, settings=JWT, claims={"roles": ["admin"]})

    access = decode_token(pair.access_token, expected=TokenType.ACCESS, settings=JWT)
    refresh = decode_token(pair.refresh_token, expected=TokenType.REFRESH, settings=JWT)

    assert access.payload["roles"] == ["admin"]
    assert "roles" not in refresh.payload


def test_reserved_claims_cannot_be_overridden() -> None:
    """Иначе вызывающий незаметно подменил бы срок жизни или владельца токена."""
    with pytest.raises(ValueError, match="Reserved JWT claims"):
        issue_tokens(ACTOR, settings=JWT, claims={"exp": 0})


def test_a_refresh_token_is_not_accepted_as_access() -> None:
    """Иначе долгоживущий refresh стал бы вечным пропуском ко всем ручкам."""
    pair = issue_tokens(ACTOR, settings=JWT)

    with pytest.raises(Unauthorized) as error:
        decode_token(pair.refresh_token, expected=TokenType.ACCESS, settings=JWT)

    assert error.value.extra["reason"] == "wrong-token-type"


def test_an_access_token_is_not_accepted_as_refresh() -> None:
    pair = issue_tokens(ACTOR, settings=JWT)

    with pytest.raises(Unauthorized):
        decode_token(pair.access_token, expected=TokenType.REFRESH, settings=JWT)


def test_an_expired_token_is_rejected() -> None:
    expired = _sign(
        {"sub": str(ACTOR), "typ": "access", "jti": str(uuid4())}, age=timedelta(hours=2)
    )

    with pytest.raises(Unauthorized) as error:
        decode_token(expired, expected=TokenType.ACCESS, settings=JWT)

    assert error.value.extra["reason"] == "expired"


def test_a_token_signed_with_another_secret_is_rejected() -> None:
    stranger = JwtSettings(secret=SecretStr("fedcba9876543210fedcba9876543210"))
    pair = issue_tokens(ACTOR, settings=stranger)

    with pytest.raises(Unauthorized) as error:
        decode_token(pair.access_token, expected=TokenType.ACCESS, settings=JWT)

    assert error.value.extra["reason"] == "malformed"


def test_an_unsigned_token_is_rejected() -> None:
    """`alg: none` — классический способ снять подпись целиком."""
    unsigned = jwt.encode(
        {"sub": str(ACTOR), "typ": "access", "jti": str(uuid4()), "iat": 0, "exp": 1 << 32},
        key="",
        algorithm="none",
    )

    with pytest.raises(Unauthorized):
        decode_token(unsigned, expected=TokenType.ACCESS, settings=JWT)


@pytest.mark.parametrize("missing", ["sub", "typ", "jti", "exp"])
def test_a_token_without_a_required_claim_is_rejected(missing: str) -> None:
    """Токен без любого из обязательных членов — не наш, каким бы валидным ни был."""
    claims: dict[str, Any] = {"sub": str(ACTOR), "typ": "access", "jti": str(uuid4())}
    claims.pop(missing, None)
    token = _sign(claims, age=timedelta(0), drop_exp=missing == "exp")

    with pytest.raises(Unauthorized):
        decode_token(token, expected=TokenType.ACCESS, settings=JWT)


def test_a_non_uuid_subject_is_rejected() -> None:
    token = _sign({"sub": "not-a-uuid", "typ": "access", "jti": str(uuid4())}, age=timedelta(0))

    with pytest.raises(Unauthorized):
        decode_token(token, expected=TokenType.ACCESS, settings=JWT)


def test_refresh_returns_a_new_usable_pair() -> None:
    issued = issue_tokens(ACTOR, settings=JWT)

    renewed = refresh_tokens(issued.refresh_token, settings=JWT)

    assert renewed.access_token != issued.access_token
    assert renewed.refresh_token != issued.refresh_token
    assert (
        decode_token(renewed.access_token, expected=TokenType.ACCESS, settings=JWT).subject == ACTOR
    )


def test_an_access_token_cannot_be_exchanged_for_a_new_pair() -> None:
    issued = issue_tokens(ACTOR, settings=JWT)

    with pytest.raises(Unauthorized):
        refresh_tokens(issued.access_token, settings=JWT)


def test_the_default_secret_is_refused_in_production(monkeypatch: pytest.MonkeyPatch) -> None:
    """Секрет из репозитория в проде означает, что токены подделывает кто угодно."""
    monkeypatch.setattr(settings, "app_env", "prod")

    with pytest.raises(ValidationError, match="JWT_SECRET is still the template default"):
        JwtSettings(secret=SecretStr(DEFAULT_SECRET))


def test_a_real_secret_is_fine_in_production(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(settings, "app_env", "prod")

    assert JwtSettings(secret=SecretStr("0123456789abcdef0123456789abcdef")).algorithm == "HS256"


def test_the_default_secret_is_fine_outside_production(monkeypatch: pytest.MonkeyPatch) -> None:
    """Иначе шаблон нельзя было бы запустить сразу после clone."""
    monkeypatch.setattr(settings, "app_env", "local")

    assert JwtSettings(secret=SecretStr(DEFAULT_SECRET)).secret.get_secret_value() == DEFAULT_SECRET


def _sign(claims: dict[str, Any], *, age: timedelta, drop_exp: bool = False) -> str:
    """Подписать произвольную нагрузку: нужно для заведомо негодных токенов."""
    issued_at = datetime.now(tz=UTC) - age
    payload = dict(claims)
    payload["iat"] = issued_at
    if not drop_exp:
        payload["exp"] = issued_at + timedelta(hours=1)
    return jwt.encode(payload, JWT.secret.get_secret_value(), algorithm=JWT.algorithm)
