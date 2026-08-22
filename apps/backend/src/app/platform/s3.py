"""Объектное хранилище: клиент S3 и bucket-aware операции над объектами.

Обычный `/files` flow передаёт содержимое напрямую по подписанной ссылке.
Framework-neutral multipart primitives ниже нужны только документированным
aggregate routes: бизнес-оркестрации и FastAPI-зависимостей здесь нет.

Подпись считается локально, без единого обращения к хранилищу: `presigned_put`
и `presigned_get` — это HMAC над строкой запроса, и botocore умеет собрать его
сам. Это не оптимизация: ссылка выдаётся внутри HTTP-запроса рядом с открытой
транзакцией, а поход в сеть оттуда нарушил бы правило «внутри транзакции
только БД».

Бизнес-логики здесь нет: ни правил именования ключей, ни ограничений на типы и
размеры, ни записи в БД. Всё это принадлежит модулю, который хранилищем
пользуется.
"""

from collections.abc import AsyncIterator, Sequence
from contextlib import AbstractAsyncContextManager, AsyncExitStack, asynccontextmanager
from dataclasses import dataclass
from datetime import datetime
from typing import TYPE_CHECKING, Final

from aiobotocore.config import AioConfig
from aiobotocore.session import AioSession, get_session
from botocore.exceptions import ClientError
from pydantic import Field
from pydantic_settings import BaseSettings, SettingsConfigDict

if TYPE_CHECKING:
    # types-aiobotocore нужен только проверке типов и живёт в dev-группе:
    # боевой образ ставится с --no-dev, и рантайм-импорт уронил бы контейнер
    # на старте. Аннотации ниже строковые по той же причине.
    from types_aiobotocore_s3.client import S3Client

#: Коды, которыми S3 сообщает об отсутствующем объекте. У ответа на HEAD нет
#: тела, поэтому botocore не может достать код ошибки из XML и подставляет
#: "404"; GET и совместимые хранилища присылают именованные коды.
_NOT_FOUND_CODES: Final = frozenset({"404", "NoSuchKey", "NotFound"})
_NO_SUCH_UPLOAD_CODES: Final = frozenset({"404", "NoSuchUpload", "NotFound"})


class S3Settings(BaseSettings):
    """Настройки объектного хранилища."""

    model_config = SettingsConfigDict(
        env_prefix="s3_",
        env_file=".env",
        env_file_encoding="utf-8",
        extra="ignore",
    )

    endpoint_url: str = "http://localhost:9000"

    #: Адрес хранилища, видимый клиенту. Пустая строка — подписывать по
    #: `endpoint_url`.
    #:
    #: Внутри compose приложение ходит в хранилище по имени сервиса
    #: (`http://minio:9000`), но подпись SigV4 накрывает заголовок Host: та же
    #: ссылка, открытая в браузере, придёт с другим Host и получит
    #: SignatureDoesNotMatch. Подменить хост в готовой ссылке нельзя по той же
    #: причине, поэтому ссылки подписываются отдельным клиентом, настроенным
    #: на публичный адрес.
    public_endpoint_url: str = ""

    region: str = "us-east-1"
    access_key: str = "minioadmin"
    # Дефолт совпадает с .env.example, чтобы шаблон работал сразу после clone
    # против локального MinIO. Это общеизвестный логин докер-образа, а не
    # секрет: в prod значение приходит из окружения.
    secret_key: str = "minioadmin"  # noqa: S105
    bucket: str = "app-files"

    #: Время жизни подписанной ссылки в секундах. Короткая ссылка ограничивает
    #: ущерб от утечки из логов и истории браузера, длинная нужна медленным
    #: клиентам; 15 минут — компромисс, который переопределяют в окружении.
    presign_ttl: int = Field(default=900, ge=1)


#: Единственный экземпляр настроек процесса. Клиент здесь не создаётся.
s3_settings = S3Settings()


@dataclass(frozen=True, slots=True)
class ObjectInfo:
    """Метаданные объекта, полученные HEAD-запросом."""

    size: int
    content_type: str
    etag: str
    last_modified: datetime


@dataclass(frozen=True, slots=True)
class ObjectEntry:
    """Строка листинга. Без `content_type`: S3 его в листинге не отдаёт."""

    key: str
    size: int
    etag: str
    last_modified: datetime


@dataclass(frozen=True, slots=True)
class CompletedPart:
    """ETag и номер завершённой части multipart upload."""

    part_number: int
    etag: str


@asynccontextmanager
async def storage(config: S3Settings) -> AsyncIterator["ObjectStorage"]:
    """Открыть клиент хранилища на время работы блока.

    Принимает настройки, отдаёт готовый `ObjectStorage`, при выходе закрывает
    соединения клиента.

    Клиент долгоживущий и создаётся один раз на процесс: он держит пул
    HTTP-соединений и разбирает описание сервиса (несколько мегабайт JSON) при
    создании. Делать это на каждый запрос — самый дорогой способ подписать
    ссылку.

    Явный вызов, а не глобальный объект: на импорте модуля клиент создаваться
    не должен, иначе процесс uvicorn получал бы его вместе с любым импортом.

    Клиентов может получиться два: рабочий и подписывающий. Второй появляется
    только когда публичный адрес хранилища отличается от внутреннего —
    подпись накрывает Host, и ссылку для браузера обязан подписать клиент,
    настроенный на тот адрес, по которому браузер придёт. Сети создание
    второго клиента не касается: запросов он не делает, только подписывает.
    """
    session = get_session()
    async with AsyncExitStack() as stack:
        client = await stack.enter_async_context(_client(session, config, config.endpoint_url))
        signer = client
        public = config.public_endpoint_url
        if public and public != config.endpoint_url:
            signer = await stack.enter_async_context(_client(session, config, public))
        yield ObjectStorage(
            client=client,
            signer=signer,
            bucket=config.bucket,
            presign_ttl=config.presign_ttl,
        )


def _client(
    session: AioSession,
    config: S3Settings,
    endpoint_url: str,
) -> AbstractAsyncContextManager["S3Client"]:
    """Создать клиент S3 на заданный адрес.

    Принимает сессию aiobotocore, настройки и адрес хранилища, возвращает
    асинхронный контекстный менеджер клиента. Соединений не открывает.
    """
    return session.create_client(
        "s3",
        endpoint_url=endpoint_url,
        region_name=config.region,
        aws_access_key_id=config.access_key,
        aws_secret_access_key=config.secret_key,
        config=AioConfig(
            # v4 обязателен: MinIO и большинство совместимых хранилищ не
            # принимают подписи v2, а botocore выбирает её для нестандартного
            # endpoint не всегда предсказуемо.
            signature_version="s3v4",
            # Path-style: у локального MinIO и у большинства self-hosted
            # инсталляций нет wildcard-DNS под virtual-host адресацию.
            s3={"addressing_style": "path"},
        ),
    )


@dataclass(frozen=True, slots=True)
class ObjectStorage:
    """S3 primitives с configured default и явным bucket override.

    Общий файловый lifecycle всегда передаёт сохранённый bucket явно. Default
    остаётся только для health-check и новых объектов до сохранения metadata.
    """

    #: Клиент запросов: по нему идут HEAD, DELETE и всё остальное.
    client: "S3Client"

    #: Клиент подписи. Совпадает с `client`, пока публичный адрес хранилища не
    #: задан отдельно; различаются они, когда приложение и клиент видят
    #: хранилище по разным адресам.
    signer: "S3Client"

    bucket: str
    presign_ttl: int

    async def presigned_put(
        self,
        key: str,
        *,
        bucket: str | None = None,
        content_type: str | None = None,
        expires_in: int | None = None,
    ) -> str:
        """Ссылка, по которой клиент сам зальёт объект.

        Принимает ключ, необязательный тип содержимого и время жизни ссылки,
        возвращает URL для метода PUT. Сети не касается.

        `content_type` попадает в подпись: клиент обязан прислать ровно этот
        заголовок, иначе хранилище отвергнет запрос. Это единственный способ
        не дать загрузить исполняемый файл под видом картинки — проверять тип
        после загрузки поздно, объект уже лежит.
        """
        params: dict[str, str] = {"Bucket": self._bucket(bucket), "Key": key}
        if content_type is not None:
            params["ContentType"] = content_type
        return await self.signer.generate_presigned_url(
            "put_object",
            Params=params,
            ExpiresIn=expires_in if expires_in is not None else self.presign_ttl,
        )

    async def presigned_get(
        self,
        key: str,
        *,
        bucket: str | None = None,
        expires_in: int | None = None,
        download_name: str | None = None,
    ) -> str:
        """Ссылка, по которой клиент сам скачает объект.

        Принимает ключ, время жизни ссылки и имя файла для скачивания,
        возвращает URL для метода GET. Сети не касается.

        `download_name` подменяет `Content-Disposition` в ответе хранилища:
        ключ объекта обычно машинный (uuid), а пользователь должен получить
        файл с осмысленным именем.
        """
        params: dict[str, str] = {"Bucket": self._bucket(bucket), "Key": key}
        if download_name is not None:
            params["ResponseContentDisposition"] = f'attachment; filename="{download_name}"'
        return await self.signer.generate_presigned_url(
            "get_object",
            Params=params,
            ExpiresIn=expires_in if expires_in is not None else self.presign_ttl,
        )

    async def head_object(self, key: str, *, bucket: str | None = None) -> ObjectInfo | None:
        """Метаданные объекта или `None`, если его нет.

        Принимает ключ, возвращает размер, тип, ETag и время изменения.
        Кидает `botocore.exceptions.ClientError` на любой ошибке, кроме
        отсутствия объекта.

        `None`, а не `NotFound` из ядра: HEAD зовут именно для того, чтобы
        узнать, появился ли объект. «Не появился» — штатный ответ на вопрос, а
        не сбой, и превращать его в исключение значило бы заставить каждого
        вызывающего оборачивать нормальный путь в try. Решение «отсутствие
        объекта — ошибка бизнеса» принимает модуль: он и поднимет `NotFound`.
        """
        try:
            response = await self.client.head_object(Bucket=self._bucket(bucket), Key=key)
        except ClientError as error:
            if _is_not_found(error):
                return None
            raise
        return ObjectInfo(
            size=response["ContentLength"],
            content_type=response.get("ContentType", "application/octet-stream"),
            etag=response["ETag"].strip('"'),
            last_modified=response["LastModified"],
        )

    async def delete_object(self, key: str, *, bucket: str | None = None) -> None:
        """Удалить объект.

        Принимает ключ, ничего не возвращает. Удаление несуществующего объекта
        не ошибка — так устроен сам протокол S3, и повторная уборка одного и
        того же ключа проходит молча.
        """
        await self.client.delete_object(Bucket=self._bucket(bucket), Key=key)

    async def list_prefix(
        self,
        prefix: str,
        *,
        bucket: str | None = None,
        limit: int = 1000,
    ) -> list[ObjectEntry]:
        """Первые объекты с заданным префиксом.

        Принимает префикс и предел числа записей, возвращает список строк
        листинга в порядке, который вернуло хранилище.

        Одна страница, а не полный обход: листинг всего бакета в память —
        готовая авария на большом хранилище. Задаче уборки хватает страницы за
        проход, а тому, кому нужен полный обход, нужен и курсор, который
        появится вместе с таким сценарием.
        """
        response = await self.client.list_objects_v2(
            Bucket=self._bucket(bucket),
            Prefix=prefix,
            MaxKeys=limit,
        )
        return [
            ObjectEntry(
                key=item["Key"],
                size=item["Size"],
                etag=item["ETag"].strip('"'),
                last_modified=item["LastModified"],
            )
            for item in response.get("Contents", [])
        ]

    async def create_multipart_upload(
        self,
        key: str,
        *,
        bucket: str,
        content_type: str,
    ) -> str:
        """Создать multipart upload в явном bucket и вернуть upload id."""
        response = await self.client.create_multipart_upload(
            Bucket=bucket,
            Key=key,
            ContentType=content_type,
        )
        return str(response["UploadId"])

    async def upload_part(
        self,
        key: str,
        upload_id: str,
        part_number: int,
        body: bytes,
        *,
        bucket: str,
    ) -> str:
        """Загрузить одну multipart part в явный bucket и вернуть ETag."""
        response = await self.client.upload_part(
            Bucket=bucket,
            Key=key,
            UploadId=upload_id,
            PartNumber=part_number,
            Body=body,
        )
        return str(response["ETag"]).strip('"')

    async def complete_multipart_upload(
        self,
        key: str,
        upload_id: str,
        parts: Sequence[CompletedPart],
        *,
        bucket: str,
    ) -> str:
        """Завершить multipart upload с частями в порядке PartNumber."""
        ordered = sorted(parts, key=lambda part: part.part_number)
        response = await self.client.complete_multipart_upload(
            Bucket=bucket,
            Key=key,
            UploadId=upload_id,
            MultipartUpload={
                "Parts": [{"ETag": part.etag, "PartNumber": part.part_number} for part in ordered]
            },
        )
        return str(response["ETag"]).strip('"')

    async def abort_multipart_upload(
        self,
        key: str,
        upload_id: str,
        *,
        bucket: str,
    ) -> None:
        """Idempotently abort конкретного multipart upload."""
        try:
            await self.client.abort_multipart_upload(
                Bucket=bucket,
                Key=key,
                UploadId=upload_id,
            )
        except ClientError as error:
            if error.response["Error"].get("Code") in _NO_SUCH_UPLOAD_CODES:
                return
            raise

    async def list_multipart_upload_ids(self, key: str, *, bucket: str) -> list[str]:
        """Найти незавершённые uploads только для точных bucket и key."""
        response = await self.client.list_multipart_uploads(Bucket=bucket, Prefix=key)
        upload_ids: list[str] = []
        while True:
            upload_ids.extend(
                str(upload["UploadId"])
                for upload in response.get("Uploads", [])
                if upload.get("Key") == key
            )
            if not response.get("IsTruncated"):
                return upload_ids
            response = await self.client.list_multipart_uploads(
                Bucket=bucket,
                Prefix=key,
                KeyMarker=str(response["NextKeyMarker"]),
                UploadIdMarker=str(response["NextUploadIdMarker"]),
            )

    async def abort_multipart_uploads_for_key(self, key: str, *, bucket: str) -> None:
        """Abort все uploads точного key для crash-gap до записи upload id."""
        for upload_id in await self.list_multipart_upload_ids(key, bucket=bucket):
            await self.abort_multipart_upload(key, upload_id, bucket=bucket)

    def _bucket(self, bucket: str | None) -> str:
        """Вернуть явный bucket либо configured default для legacy primitives."""
        return bucket if bucket is not None else self.bucket


def _is_not_found(error: ClientError) -> bool:
    """Отличить «объекта нет» от настоящего сбоя хранилища.

    Отсутствующий бакет сюда не попадает: его код `NoSuchBucket`, и это ошибка
    конфигурации, которую нельзя выдавать за «объекта нет».
    """
    return error.response["Error"].get("Code") in _NOT_FOUND_CODES
