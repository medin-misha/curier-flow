"""Двухфазная загрузка файлов: выдача ссылок, проверка объекта, уборка.

Файл не проходит через приложение ни разу. Сервис выдаёт подписанную ссылку,
клиент льёт объект прямо в хранилище, сервис потом проверяет результат
HEAD-запросом. Проксирование заняло бы воркер uvicorn на всё время передачи и
упёрлось бы в таймауты обратного прокси, а память процесса — в размер файла.

Границы транзакций держит этот модуль, а не зависимость `get_uow`. Каждая
операция здесь сочетает базу и объектное хранилище, а внешний вызов внутри
открытой транзакции недопустим: HEAD и DELETE идут по сети, и на медленном
хранилище они держали бы соединение из пула и блокировки строк всё это время.
Отсюда единый порядок: читающая сессия закрывается → поход в хранилище →
короткая пишущая транзакция. Подпись ссылки сети не касается, но и она
вынесена наружу транзакции: правило «в транзакции только БД» стоит дороже
одного лишнего вызова, а исключение из него первым делом скопируют.
"""

import time
from collections.abc import Sequence
from dataclasses import dataclass
from datetime import UTC, datetime, timedelta
from typing import Annotated, Final
from uuid import UUID

import structlog
from pydantic import Field, field_validator
from pydantic_settings import BaseSettings, NoDecode, SettingsConfigDict
from sqlalchemy import delete, select, update
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker
from uuid_utils.compat import uuid7

from app.kernel.context import actor_id
from app.kernel.db.crud import CRUD
from app.kernel.errors import NotFound, ValidationFailed
from app.kernel.events.bus import emit
from app.kernel.pagination import Page, PageParams
from app.modules.storage.events import FileConfirmed
from app.modules.storage.models import File, FileStatus
from app.modules.storage.schemas.requests import ConfirmRequest, UploadUrlRequest
from app.platform.s3 import ObjectInfo, ObjectStorage

#: Общий префикс ключей модуля. Отдельный каталог верхнего уровня: по нему
#: настраиваются правила жизненного цикла бакета и видно, что в него пишет
#: именно этот сервис.
_KEY_PREFIX: Final = "uploads"

_logger = structlog.get_logger("app.modules.storage")


class StorageSettings(BaseSettings):
    """Лимиты загрузки и расписание уборки."""

    model_config = SettingsConfigDict(
        env_prefix="storage_",
        env_file=".env",
        env_file_encoding="utf-8",
        extra="ignore",
    )

    #: Предел размера одного файла в байтах. Проверяется дважды: по заявке
    #: клиента — до выдачи ссылки, по факту — при подтверждении.
    max_file_size: int = Field(default=26_214_400, gt=0)

    #: Разрешённые типы содержимого. Белый список, а не чёрный: перечислить
    #: то, что сервису нужно, короче и безопаснее, чем угадывать все опасные
    #: типы. `NoDecode` отключает разбор значения как JSON — в окружении тип
    #: перечисляется через запятую, а не списком JSON.
    allowed_content_types: Annotated[frozenset[str], NoDecode] = frozenset(
        {"image/png", "image/jpeg", "image/webp", "application/pdf"}
    )

    #: Сколько секунд ждать загрузку, прежде чем считать `pending` брошенной.
    #: Заметно больше времени жизни подписанной ссылки: пока ссылка жива,
    #: клиент вправе долить файл.
    orphan_ttl: int = Field(default=3600, gt=0)

    #: Когда собирать брошенные загрузки, в формате cron (UTC).
    orphan_sweep_cron: str = "*/15 * * * *"

    #: Как часто удалять помеченные файлы, в секундах. Это же — задержка между
    #: ответом на DELETE и исчезновением объекта из бакета.
    deletion_interval: int = Field(default=60, ge=1)

    #: Сколько файлов задача обрабатывает за один проход. Ограничение по
    #: времени прохода: каждый файл — это отдельный запрос к хранилищу.
    batch_size: int = Field(default=100, ge=1)

    @field_validator("allowed_content_types", mode="before")
    @classmethod
    def _split_types(cls, value: object) -> object:
        """Разобрать список типов из переменной окружения.

        Принимает строку `image/png, application/pdf` либо уже готовую
        коллекцию, возвращает множество типов в нижнем регистре.
        """
        if isinstance(value, str):
            return {item.strip().lower() for item in value.split(",") if item.strip()}
        return value


#: Единственный экземпляр настроек процесса.
storage_settings = StorageSettings()


@dataclass(frozen=True, slots=True)
class FileStorage:
    """Хранилище и лимиты модуля: всё, что нужно сервису кроме базы.

    Собирается один раз — в lifespan модуля для процесса uvicorn и на каждый
    запуск задачи в воркере — и передаётся в сервис аргументом.
    """

    objects: ObjectStorage
    limits: StorageSettings


@dataclass(frozen=True, slots=True)
class UploadTicket:
    """Созданная строка и ссылка, по которой клиент зальёт объект."""

    file: File
    upload_url: str
    expires_in: int


@dataclass(frozen=True, slots=True)
class FileLink:
    """Метаданные файла и ссылка на скачивание, если файл готов."""

    file: File
    download_url: str | None


async def create_upload(
    request: UploadUrlRequest,
    *,
    session_factory: async_sessionmaker[AsyncSession],
    storage: FileStorage,
) -> UploadTicket:
    """Завести строку `pending` и подписать ссылку на загрузку.

    Принимает заявку клиента, фабрику сессий и хранилище, возвращает строку
    вместе со ссылкой. Кидает `ValidationFailed`, если тип или размер выходят
    за лимиты модуля, — строка в этом случае не создаётся.

    Транзакция закрывается до того, как ссылка попадёт клиенту: с этого
    момента объект может появиться в бакете в любую секунду, и строка про него
    обязана уже существовать. Иначе подтверждать будет нечего, а объект
    остался бы в бакете навсегда — уборка ищет сирот по строкам.
    """
    content_type = request.content_type.lower()
    _check_declared(request, content_type, storage.limits)

    file_id = uuid7()
    key = _build_key(file_id)
    async with session_factory() as session, session.begin():
        file = await CRUD.create(
            File,
            request,
            session,
            id=file_id,
            bucket=storage.objects.bucket,
            key=key,
            content_type=content_type,
            status=FileStatus.PENDING,
            owner_id=actor_id.get(),
        )

    url = await storage.objects.presigned_put(key, content_type=content_type)
    return UploadTicket(file=file, upload_url=url, expires_in=storage.objects.presign_ttl)


async def confirm_upload(
    file_id: UUID,
    request: ConfirmRequest,
    *,
    session_factory: async_sessionmaker[AsyncSession],
    storage: FileStorage,
) -> File:
    """Проверить загруженный объект и перевести файл в `ready`.

    Принимает идентификатор файла, ETag от хранилища, фабрику сессий и
    хранилище, возвращает обновлённую строку. Кидает `NotFound`, если строки
    нет, файл удаляется или объект так и не появился в бакете, и
    `ValidationFailed`, если объект не совпал с заявкой — такой объект
    удаляется из бакета сразу.

    Повторное подтверждение готового файла — не ошибка, а обычный ретрай
    клиента после обрыва: строка возвращается как есть, второго события не
    возникает. Проверка объекта при этом не повторяется — иначе ретрай с
    неудачным ETag удалил бы содержимое уже принятого файла.

    Порядок шагов важен: сначала читаем состояние и закрываем сессию, потом
    идём в хранилище, и только потом открываем пишущую транзакцию. Смена
    статуса и `emit` происходят в ней вместе, поэтому событие не может уехать
    без файла, а файл — стать готовым без события.
    """
    async with session_factory() as session:
        file = await CRUD.get_or_404(File, file_id, session)
    _ensure_present(file)
    if file.status is FileStatus.READY:
        return file

    info = await storage.objects.head_object(file.key)
    if info is None:
        raise NotFound(
            "Uploaded object not found in the bucket",
            resource=File.__name__,
            pk=str(file_id),
        )
    await _accept_or_discard(file, info, request.etag, storage=storage)

    async with session_factory() as session, session.begin():
        row = await CRUD.get_or_404(File, file_id, session)
        if row.status is FileStatus.READY:
            return row
        _ensure_present(row)
        row.status = FileStatus.READY
        row.etag = info.etag
        emit(session, _confirmed(row))
    return row


async def get_file(
    file_id: UUID,
    *,
    session_factory: async_sessionmaker[AsyncSession],
    storage: FileStorage,
) -> FileLink:
    """Отдать метаданные файла и ссылку на скачивание.

    Принимает идентификатор, фабрику сессий и хранилище, возвращает строку и
    подписанную ссылку (`None`, пока файл не готов). Кидает `NotFound`, если
    строки нет или файл помечен к удалению.
    """
    async with session_factory() as session:
        file = await CRUD.get_or_404(File, file_id, session)
    _ensure_present(file)

    if file.status is not FileStatus.READY:
        return FileLink(file=file, download_url=None)
    url = await storage.objects.presigned_get(file.key, download_name=file.original_name)
    return FileLink(file=file, download_url=url)


async def list_files(
    page: PageParams,
    *,
    session_factory: async_sessionmaker[AsyncSession],
) -> Page[File]:
    """Вернуть страницу файлов, кроме помеченных к удалению.

    Принимает параметры страницы и фабрику сессий, возвращает keyset-страницу.

    Фильтра по владельцу нет намеренно: `owner_id` заполнится, когда появится
    аутентификация, и вместе с фильтром понадобится индекс
    `(owner_id, created_at DESC, id DESC)` — раньше он был бы мёртвым грузом.
    """
    async with session_factory() as session:
        return await CRUD.list_page(
            File,
            session,
            page=page,
            where=(File.status != FileStatus.DELETING,),
        )


async def mark_for_deletion(
    file_id: UUID,
    *,
    session_factory: async_sessionmaker[AsyncSession],
) -> None:
    """Пометить файл к удалению.

    Принимает идентификатор и фабрику сессий, ничего не возвращает. Кидает
    `NotFound`, если строки нет; повторный вызов на уже помеченном файле
    проходит молча.

    Объект остаётся в бакете до прохода задачи. Удалять его прямо здесь
    нельзя: это сеть внутри запроса, а поставить задачу через `kiq()` —
    обращение к брокеру внутри транзакции. Клиенту файл при этом уже не виден.
    """
    async with session_factory() as session, session.begin():
        file = await CRUD.get_or_404(File, file_id, session)
        # Повторный вызов ничего не стоит: значение то же, и SQLAlchemy не
        # отправит UPDATE, — поэтому отдельной проверки «уже помечен» нет.
        file.status = FileStatus.DELETING


async def sweep_orphans(
    *,
    session_factory: async_sessionmaker[AsyncSession],
    storage: FileStorage,
) -> int:
    """Убрать брошенные загрузки: строки `pending` старше TTL и их объекты.

    Принимает фабрику сессий и хранилище, возвращает число убранных файлов.
    Не кидает: отказ хранилища по одному файлу — запись в лог, а не падение
    периодической задачи.

    Клиент вправе исчезнуть в любой момент между получением ссылки и
    подтверждением. Без этой уборки в базе копились бы вечные `pending`, а в
    бакете — объекты, о которых никто не помнит.
    """
    cutoff = datetime.now(tz=UTC) - timedelta(seconds=storage.limits.orphan_ttl)
    doomed = await _claim_orphans(session_factory, cutoff, limit=storage.limits.batch_size)
    return await _purge(doomed, session_factory=session_factory, storage=storage)


async def delete_marked(
    *,
    session_factory: async_sessionmaker[AsyncSession],
    storage: FileStorage,
) -> int:
    """Физически удалить файлы, помеченные к удалению.

    Принимает фабрику сессий и хранилище, возвращает число удалённых файлов.
    Не кидает по тем же причинам, что и сборщик сирот.
    """
    doomed = await _claim_deleting(session_factory, limit=storage.limits.batch_size)
    return await _purge(doomed, session_factory=session_factory, storage=storage)


def _build_key(file_id: UUID) -> str:
    """Ключ объекта в бакете: `uploads/ГГГГ/ММ/ДД/<id>`.

    Ключ генерирует сервер: клиент, задающий ключ, перезаписал бы чужой
    объект. Дата в префиксе разбивает бакет на каталоги по дням — иначе весь
    сервис живёт в одном каталоге, который не посмотреть консолью и не накрыть
    отдельным правилом жизненного цикла.

    Расширения в ключе нет: имя для скачивания задаёт `Content-Disposition`
    подписанной ссылки, а тип содержимого хранится колонкой. Подставлять в
    ключ оригинальное имя нельзя — оно приходит от пользователя.
    """
    today = datetime.now(tz=UTC)
    return f"{_KEY_PREFIX}/{today:%Y/%m/%d}/{file_id}"


def _check_declared(
    request: UploadUrlRequest,
    content_type: str,
    limits: StorageSettings,
) -> None:
    """Проверить заявку клиента по лимитам модуля.

    Принимает заявку, нормализованный тип содержимого и лимиты, ничего не
    возвращает. Кидает `ValidationFailed`, если тип не разрешён или размер
    больше предела.

    Проверка до выдачи ссылки, а не после загрузки: иначе клиент сначала
    зальёт сотню мегабайт и только потом узнает, что их не примут.
    """
    if content_type not in limits.allowed_content_types:
        raise ValidationFailed(
            "Content type is not allowed",
            content_type=request.content_type,
            allowed=sorted(limits.allowed_content_types),
        )
    if request.size > limits.max_file_size:
        raise ValidationFailed(
            "Declared size exceeds the limit",
            size=request.size,
            limit=limits.max_file_size,
        )


def _ensure_present(file: File) -> None:
    """Убедиться, что файл ещё существует для клиента.

    Кидает `NotFound`, если файл помечен к удалению. Именно 404, а не 409:
    ответив на DELETE, сервис пообещал, что файла больше нет, и остальные
    ручки обязаны отвечать так же. Воскрешать строку, объект которой вот-вот
    удалит задача, нельзя — получился бы готовый файл без содержимого.
    """
    if file.status is FileStatus.DELETING:
        raise NotFound("File not found", resource=File.__name__, pk=str(file.id))


async def _accept_or_discard(
    file: File,
    info: ObjectInfo,
    claimed_etag: str,
    *,
    storage: FileStorage,
) -> None:
    """Сверить объект с заявкой, а не совпавший — удалить из бакета.

    Принимает строку, метаданные объекта, ETag от клиента и хранилище, ничего
    не возвращает. Кидает `ValidationFailed` после удаления объекта.

    Удаление именно здесь, а не «потом уборкой»: строка остаётся `pending`,
    клиент вправе перезалить файл по той же ссылке, и старый объект под тем же
    ключом никому не нужен уже сейчас.
    """
    reason = _mismatch(file, info, claimed_etag, storage.limits)
    if reason is None:
        return

    await storage.objects.delete_object(file.key)
    _logger.warning(
        "storage.upload_rejected",
        file_id=str(file.id),
        key=file.key,
        reason=reason,
    )
    raise ValidationFailed("Uploaded object does not match the upload request", reason=reason)


def _mismatch(
    file: File,
    info: ObjectInfo,
    claimed_etag: str,
    limits: StorageSettings,
) -> str | None:
    """Первое расхождение объекта с заявкой или `None`, если всё сошлось.

    Тип содержимого сверяется, потому что он вшит в подпись ссылки: хранилище
    не приняло бы PUT с другим заголовком, и расхождение здесь означает, что
    объект под этим ключом появился не тем путём, которым мы его ждали.

    ETag сверяется с тем, что клиенту вернуло само хранилище: совпадение
    доказывает, что клиент говорит именно про свою загрузку, а не про
    случившуюся раньше чужую.
    """
    if info.size > limits.max_file_size:
        return f"size {info.size} exceeds the limit of {limits.max_file_size} bytes"
    if info.size != file.size:
        return f"size {info.size} differs from the declared {file.size}"
    if info.content_type.lower() != file.content_type:
        return f"content type {info.content_type!r} differs from the declared {file.content_type!r}"
    if info.etag.lower() != claimed_etag.strip('"').lower():
        return "etag does not match the one reported by the client"
    return None


def _confirmed(file: File) -> FileConfirmed:
    """Собрать событие о подтверждённом файле."""
    return FileConfirmed(
        file_id=file.id,
        bucket=file.bucket,
        key=file.key,
        original_name=file.original_name,
        content_type=file.content_type,
        size=file.size,
        owner_id=file.owner_id,
    )


async def _claim_orphans(
    session_factory: async_sessionmaker[AsyncSession],
    cutoff: datetime,
    *,
    limit: int,
) -> Sequence[tuple[UUID, str]]:
    """Пометить брошенные загрузки к удалению и вернуть их ключи.

    Принимает фабрику сессий, отсечку по времени и размер пачки, возвращает
    пары «идентификатор, ключ».

    Пометка, а не прямое удаление: она отбирает строку у гонки. С момента
    коммита `pending` перестаёт существовать для клиента, и опоздавшее
    подтверждение уже не сделает готовым файл, объект которого мы вот-вот
    удалим. Если процесс умрёт следующей строкой, помеченные файлы доберёт
    задача удаления — потерять их нельзя.
    """
    doomed = (
        select(File.id)
        .where(File.status == FileStatus.PENDING, File.created_at < cutoff)
        .order_by(File.created_at)
        .limit(limit)
        # Строки, которые прямо сейчас правит чужая транзакция, пропускаем:
        # ждать их незачем, они попадут в следующий проход.
        .with_for_update(skip_locked=True)
        .scalar_subquery()
    )
    statement = (
        update(File)
        .where(File.id.in_(doomed))
        .values(status=FileStatus.DELETING)
        .returning(File.id, File.key)
        .execution_options(synchronize_session=False)
    )
    async with session_factory() as session, session.begin():
        return [(row.id, row.key) for row in (await session.execute(statement)).all()]


async def _claim_deleting(
    session_factory: async_sessionmaker[AsyncSession],
    *,
    limit: int,
) -> Sequence[tuple[UUID, str]]:
    """Забрать пачку помеченных к удалению файлов.

    Принимает фабрику сессий и размер пачки, возвращает пары «идентификатор,
    ключ».

    Блокировка снимается вместе с транзакцией, и это допустимо: из `deleting`
    возврата нет, а повторная уборка одного файла двумя воркерами безвредна —
    и удаление объекта, и удаление строки идемпотентны.
    """
    statement = (
        select(File.id, File.key)
        .where(File.status == FileStatus.DELETING)
        .order_by(File.created_at)
        .limit(limit)
        .with_for_update(skip_locked=True)
    )
    async with session_factory() as session, session.begin():
        return [(row.id, row.key) for row in (await session.execute(statement)).all()]


async def _purge(
    doomed: Sequence[tuple[UUID, str]],
    *,
    session_factory: async_sessionmaker[AsyncSession],
    storage: FileStorage,
) -> int:
    """Удалить объекты и строки помеченных файлов.

    Принимает пары «идентификатор, ключ», фабрику сессий и хранилище,
    возвращает число полностью убранных файлов.

    Порядок обязателен: сперва объект, потом строка. В обратном порядке сбой
    между шагами терял бы объект навсегда — ключ хранится только в строке, и
    без неё найти его в бакете уже нечем.

    Отказ по одному файлу не прекращает проход: строка остаётся `deleting` и
    попадёт в следующий, а остальные файлы уборку заслужили не меньше.
    """
    purged = 0
    started = time.perf_counter()
    for file_id, key in doomed:
        try:
            await storage.objects.delete_object(key)
        except Exception as error:
            # Способов отказать у сети столько же, сколько библиотек внизу, и
            # свести их к «этот файл убрать не удалось» больше негде.
            _logger.warning(
                "storage.object_delete_failed",
                file_id=str(file_id),
                key=key,
                error=f"{type(error).__name__}: {error}",
            )
            continue
        await _forget(file_id, session_factory)
        purged += 1

    if purged:
        _logger.info(
            "storage.purged",
            files=purged,
            selected=len(doomed),
            duration_ms=round((time.perf_counter() - started) * 1000, 3),
        )
    return purged


async def _forget(file_id: UUID, session_factory: async_sessionmaker[AsyncSession]) -> None:
    """Удалить строку файла, объект которого уже удалён."""
    async with session_factory() as session, session.begin():
        await session.execute(delete(File).where(File.id == file_id))
