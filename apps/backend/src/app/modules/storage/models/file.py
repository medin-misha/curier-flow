"""Таблица `files`: строка на каждый объект в хранилище."""

from enum import StrEnum
from uuid import UUID

from sqlalchemy import BigInteger, Enum, Index, String, UniqueConstraint
from sqlalchemy.orm import Mapped, mapped_column

from app.kernel.db.base import Base
from app.kernel.db.mixins import TimestampMixin, UUIDPkMixin


class FileStatus(StrEnum):
    """Состояние файла в двухфазной загрузке.

    `pending` — строка создана, объекта в хранилище может ещё не быть;
    `ready` — объект загружен клиентом и проверен сервером;
    `deleting` — для клиента файл уже не существует, объект и строку уберёт
    периодическая задача.

    Из `deleting` возврата нет: подтвердить или скачать такой файл нельзя,
    иначе задача удалила бы объект из-под живой ссылки.
    """

    PENDING = "pending"
    READY = "ready"
    DELETING = "deleting"


class File(UUIDPkMixin, TimestampMixin, Base):
    """Метаданные объекта: где он лежит, что это и в каком он состоянии.

    Содержимое файла в таблице не хранится и через приложение не проходит:
    клиент льёт и качает его напрямую по подписанной ссылке.
    """

    __tablename__ = "files"

    #: Патчить нечего, и это осознанно: PATCH-ручки у модуля нет, а всё, что
    #: можно было бы менять, определяет сервер — `status`, `bucket`, `key`,
    #: `etag`. Пустой белый список означает, что случайно добавленный PATCH не
    #: пропустит ни одного поля, пока разрешение не выдадут явно.
    __patchable__ = frozenset()

    __table_args__ = (
        # Выборка обеих периодических задач: «pending старше TTL» и «deleting».
        # Один составной индекс на оба запроса: они отличаются только значением
        # статуса, а вторая колонка задаёт порядок обхода.
        Index("ix_files_status_created_at", "status", "created_at"),
        # Две строки на один объект — это потерянный объект: уборка одной из
        # них удалила бы объект из-под второй.
        UniqueConstraint("bucket", "key"),
    )

    #: Имя бакета берётся из настроек платформы и хранится в строке: бакет
    #: сервиса со временем меняют, а уже загруженные объекты остаются в старом.
    bucket: Mapped[str] = mapped_column(String(63))

    #: Ключ объекта, сгенерированный сервером. 1024 — предел длины ключа в S3.
    key: Mapped[str] = mapped_column(String(1024))

    #: Имя файла у пользователя. Хранится отдельно от ключа: в нём бывают
    #: пробелы, юникод и `../`, а подставляется оно только в
    #: `Content-Disposition` подписанной ссылки на скачивание.
    original_name: Mapped[str] = mapped_column(String(255))

    #: Тип, который клиент заявил и который вшит в подпись ссылки на загрузку:
    #: хранилище не примет объект с другим `Content-Type`.
    content_type: Mapped[str] = mapped_column(String(255))

    #: Заявленный клиентом размер; при подтверждении сверяется с фактическим.
    #: BigInteger, а не Integer: два гигабайта упираются в предел int4.
    size: Mapped[int] = mapped_column(BigInteger)

    #: ETag объекта, сверенный при подтверждении. NULL, пока файл `pending`:
    #: до загрузки его знать неоткуда.
    etag: Mapped[str | None] = mapped_column(String(128), default=None)

    #: Хранится как VARCHAR, а не как нативный тип Postgres: новое состояние
    #: файла — это правка кода, а нативный enum потребовал бы ALTER TYPE,
    #: который к тому же не откатывается внутри транзакции миграции. Значения
    #: проверяет сам тип на стороне Python, CHECK в базе не заводится (это
    #: умолчание SQLAlchemy): иначе каждый новый статус тянул бы за собой
    #: пересоздание ограничения.
    #: `values_callable` кладёт в базу значения ("pending"), а не имена членов
    #: ("PENDING"): по этой колонке читают глазами и пишут запросы руками.
    status: Mapped[FileStatus] = mapped_column(
        Enum(
            FileStatus,
            name="file_status",
            native_enum=False,
            length=16,
            values_callable=lambda enum: [member.value for member in enum],
        ),
        default=FileStatus.PENDING,
    )

    #: Владелец файла из `actor_id`. Nullable, потому что аутентификации в
    #: шаблоне ещё нет и все загрузки пока системные.
    owner_id: Mapped[UUID | None] = mapped_column(default=None)


#: Индекс под keyset-пагинацию: порядок колонок и направление обязаны совпадать
#: с `ORDER BY created_at DESC, id DESC` в `CRUD.list_page`, иначе Postgres
#: досортировывает выборку. Объявлен после класса, а не в `__table_args__`:
#: внутри тела класса колонок ещё нет, и сослаться на них выражением нельзя,
#: а строка вместо выражения потеряла бы направление сортировки.
Index("ix_files_keyset", File.created_at.desc(), File.id.desc())
