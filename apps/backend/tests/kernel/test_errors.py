"""Иерархия прикладных ошибок: коды, статусы, полезная нагрузка."""

import pytest

from app.kernel.errors import (
    AppError,
    Conflict,
    DependencyUnavailable,
    NotFound,
    PermissionDenied,
    RateLimited,
    Unauthorized,
    ValidationFailed,
)

CASES = [
    (NotFound, 404, "not-found"),
    (Conflict, 409, "conflict"),
    (ValidationFailed, 422, "validation-failed"),
    (PermissionDenied, 403, "permission-denied"),
    (Unauthorized, 401, "unauthorized"),
    (RateLimited, 429, "rate-limited"),
    (DependencyUnavailable, 503, "dependency-unavailable"),
]


@pytest.mark.parametrize(("error_type", "status", "code"), CASES)
def test_status_and_code(error_type: type[AppError], status: int, code: str) -> None:
    assert error_type.status == status
    assert error_type.code == code
    assert issubclass(error_type, AppError)


@pytest.mark.parametrize("error_type", [case[0] for case in CASES])
def test_code_is_kebab_case(error_type: type[AppError]) -> None:
    assert error_type.code == error_type.code.lower()
    assert "_" not in error_type.code
    assert " " not in error_type.code


def test_detail_defaults_to_title() -> None:
    assert NotFound().detail == NotFound.title


def test_detail_and_extra_are_kept() -> None:
    error = Conflict("Fields are not patchable: owner", fields=["owner"])
    assert error.detail == "Fields are not patchable: owner"
    assert error.extra == {"fields": ["owner"]}
    assert str(error) == "Fields are not patchable: owner"


def test_app_error_falls_back_to_500() -> None:
    """Наследник, забывший объявить статус, не должен ронять обработчик ошибок."""

    class CustomError(AppError):
        """Ошибка, не переопределившая ни одного атрибута класса."""

    assert CustomError().status == 500
    assert CustomError().code == "internal-error"
