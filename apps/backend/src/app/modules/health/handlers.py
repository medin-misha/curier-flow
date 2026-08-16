"""HTTP-ручки модуля health: liveness, readiness, информация о сборке."""

from http import HTTPStatus
from typing import Annotated, cast

from fastapi import APIRouter, Depends, Request, Response
from sqlalchemy.ext.asyncio import AsyncSession

from app.kernel.db.session import get_ro_session
from app.modules.health.schemas.responses import (
    DependencyReport,
    InfoResponse,
    LivenessResponse,
    ReadinessResponse,
)
from app.modules.health.services import (
    DependencyStatus,
    Probes,
    build_info,
    check_readiness,
)


async def no_store(response: Response) -> None:
    """Запретить кеширование ответа.

    Ручки health описывают состояние «прямо сейчас». Прокси или балансировщик,
    закешировавший 200 хотя бы на минуту, продолжит слать трафик в контейнер,
    который уже доложил о неготовности.
    """
    response.headers["cache-control"] = "no-store"


async def get_probes(request: Request) -> Probes:
    """Достать клиенты проверок, созданные lifespan модуля.

    `cast` неизбежен: `app.state` не типизирован, а без него mypy видит `Any`.
    Ключ кладёт `module.py` — единственное место, где эти клиенты создаются.
    """
    return cast(Probes, request.app.state.health_probes)


#: Сессия только для чтения. Псевдоним объявлен здесь, а не взят из
#: `app.api.deps`: правило зависимостей запрещает модулю импортировать слой api.
RoSession = Annotated[AsyncSession, Depends(get_ro_session)]
HealthProbes = Annotated[Probes, Depends(get_probes)]

router = APIRouter(tags=["health"], dependencies=[Depends(no_store)])


@router.get("/live", summary="Liveness probe")
async def live() -> LivenessResponse:
    """Ответить, что процесс жив и event loop обслуживает запросы.

    В базу, брокер и хранилище не ходит намеренно: по этой ручке оркестратор
    решает, не пора ли убить контейнер, и отказ чужого сервиса не повод его
    перезапускать.
    """
    return LivenessResponse(status="alive")


@router.get(
    "/ready",
    summary="Readiness probe",
    responses={
        HTTPStatus.SERVICE_UNAVAILABLE: {
            "model": ReadinessResponse,
            "description": "At least one dependency is unavailable",
        }
    },
)
async def ready(
    response: Response,
    probes: HealthProbes,
    session: RoSession,
) -> ReadinessResponse:
    """Опросить зависимости и доложить, можно ли слать в процесс трафик."""
    report = await check_readiness(session, probes)
    if not report.ready:
        response.status_code = HTTPStatus.SERVICE_UNAVAILABLE
    return ReadinessResponse(
        status="ready" if report.ready else "not_ready",
        dependencies=[_report(status) for status in report.dependencies],
    )


@router.get("/info", summary="Build information")
async def info(session: RoSession) -> InfoResponse:
    """Отдать имя, версию, окружение сборки и ревизию схемы БД."""
    return InfoResponse.model_validate(await build_info(session))


def _report(status: DependencyStatus) -> DependencyReport:
    """Переложить статус зависимости в схему ответа."""
    return DependencyReport(
        name=status.name,
        status="up" if status.up else "down",
        duration_ms=status.duration_ms,
        error=status.error,
    )
