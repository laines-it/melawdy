"""Small, disk-backed demonstration queue. Audio inference runs manually in Colab."""
from contextlib import contextmanager
import hashlib
import hmac
import json
import secrets
import sqlite3
import time
from pathlib import Path
from typing import Annotated, Literal
from urllib.parse import unquote
from uuid import UUID, uuid4

from fastapi import APIRouter, Depends, Header, HTTPException, Path as PathParam, Request, Response
from fastapi.responses import FileResponse
from pydantic import BaseModel, ConfigDict, Field, model_validator

from backend.config import get_settings

router = APIRouter(prefix="/api/v1/music-check", tags=["music-check"])
ALLOWED_EXTENSIONS = {".mp3", ".wav", ".flac", ".ogg", ".m4a", ".aac"}
LEASE_SECONDS = 60 * 60
MAX_PREVIEW_BYTES = 256 * 1024
MAX_PREVIEWS = 10


def digest(value: str) -> str:
    return hashlib.sha256(value.encode()).hexdigest()


def available() -> bool:
    settings = get_settings()
    return settings.music_check_enabled and len(settings.music_check_worker_token) >= 32


def enabled():
    if not available():
        raise HTTPException(503, "Демонстрационная проверка сейчас выключена")


def worker(authorization: Annotated[str, Header()] = ""):
    enabled()
    supplied = authorization.removeprefix("Bearer ") if authorization.startswith("Bearer ") else ""
    if not hmac.compare_digest(digest(supplied), digest(get_settings().music_check_worker_token)):
        raise HTTPException(401, "Неверный ключ оператора")


class Match(BaseModel):
    model_config = ConfigDict(extra="forbid", allow_inf_nan=False)
    reference: str = Field(min_length=1, max_length=255)
    distance: float = Field(ge=0, le=1e12)
    query_start: float = Field(ge=0, le=1800)
    query_end: float = Field(gt=0, le=1800)
    reference_start: float = Field(ge=0, le=86400)
    reference_end: float = Field(gt=0, le=86400)

    @model_validator(mode="after")
    def ordered(self):
        if self.query_end <= self.query_start or self.reference_end <= self.reference_start:
            raise ValueError("Конец фрагмента должен быть после начала")
        return self


class Result(BaseModel):
    model_config = ConfigDict(extra="forbid", allow_inf_nan=False)
    outcome: Literal["completed", "failed"]
    catalog_size: int = Field(default=0, ge=0, le=100000)
    matches: list[Match] = Field(default_factory=list, max_length=100)
    query_sha256: str = Field(pattern=r"^[a-f0-9]{64}$")
    query_duration_seconds: float = Field(default=0, ge=0, le=1800)
    window_seconds: float = Field(default=20, ge=1, le=120)
    hop_seconds: float = Field(default=5, gt=0, le=120)
    checkpoint_sha256: str = Field(pattern=r"^[a-f0-9]{64}$")
    configuration_sha256: str = Field(pattern=r"^[a-f0-9]{64}$")
    repo_commit: str = Field(pattern=r"^[a-f0-9]{40}$")
    message: str = Field(default="", max_length=500)

    @model_validator(mode="after")
    def consistent(self):
        if self.outcome == "completed" and (not self.catalog_size or not self.query_duration_seconds):
            raise ValueError("Укажите фактический размер проверенного каталога и длительность записи")
        if self.outcome == "failed" and self.matches:
            raise ValueError("Неуспешное задание не может содержать совпадения")
        for match in self.matches:
            if match.query_end > self.query_duration_seconds + 0.05:
                raise ValueError("Фрагмент выходит за пределы исследуемой записи")
            if (match.query_end - match.query_start > self.window_seconds + 0.05
                    or match.reference_end - match.reference_start > self.window_seconds + 0.05):
                raise ValueError("Фрагмент длиннее окна модели")
        return self


class Store:
    def __init__(self):
        self.settings = get_settings()
        self.root = Path(self.settings.music_check_data_dir).resolve()
        self.root.mkdir(parents=True, exist_ok=True, mode=0o700)
        self.db = self.root / "jobs.sqlite3"
        with self.connect() as conn:
            conn.execute("BEGIN IMMEDIATE")
            conn.execute("""CREATE TABLE IF NOT EXISTS jobs (
                id TEXT PRIMARY KEY, token_hash TEXT NOT NULL, name TEXT NOT NULL,
                status TEXT NOT NULL, created REAL NOT NULL, expires REAL NOT NULL,
                size INTEGER NOT NULL, sha256 TEXT, lease_hash TEXT, lease_until REAL,
                result TEXT
            )""")
            columns = {row["name"] for row in conn.execute("PRAGMA table_info(jobs)")}
            for name, definition in (("code", "TEXT"), ("previews", "TEXT NOT NULL DEFAULT '{}'"),
                                     ("preview_bytes", "INTEGER NOT NULL DEFAULT 0")):
                if name not in columns:
                    conn.execute(f"ALTER TABLE jobs ADD COLUMN {name} {definition}")
            conn.execute("CREATE UNIQUE INDEX IF NOT EXISTS jobs_code ON jobs(code) WHERE code IS NOT NULL")
            # Backfill only during migration, not on every status poll.
            if "code" not in columns:
                active = conn.execute("SELECT id FROM jobs WHERE expires > ? ORDER BY created", (time.time(),)).fetchall()
                for row, number in zip(active, range(10, 100)):
                    conn.execute("UPDATE jobs SET code=? WHERE id=?", (str(number), row["id"]))
        self.cleanup()

    @contextmanager
    def connect(self):
        conn = sqlite3.connect(self.db, timeout=15)
        conn.row_factory = sqlite3.Row
        try:
            with conn:
                yield conn
        finally:
            conn.close()

    def path(self, job_id):
        return self.root / (str(job_id) + ".audio")

    def clear_previews(self, row):
        for preview in json.loads(row["previews"]).values():
            (self.root / preview["file"]).unlink(missing_ok=True)

    def cleanup(self):
        now = time.time()
        with self.connect() as conn:
            conn.execute("BEGIN IMMEDIATE")
            rows = conn.execute("SELECT * FROM jobs WHERE expires <= ? AND status != 'expired'", (now,)).fetchall()
            for row in rows:
                self.clear_previews(row)
                self.path(row["id"]).unlink(missing_ok=True)
                self.path(row["id"]).with_suffix(".partial").unlink(missing_ok=True)
                for partial in self.root.glob(f"{row['id']}.*.partial"):
                    partial.unlink(missing_ok=True)
            conn.execute("UPDATE jobs SET status='expired', size=0, result=NULL, lease_hash=NULL, code=NULL, previews='{}', preview_bytes=0 WHERE expires <= ?", (now,))
            conn.execute("DELETE FROM jobs WHERE expires < ?", (now - 7 * 86400,))

    def reserve(self, name, size):
        job_id, token, now = str(uuid4()), secrets.token_urlsafe(32), time.time()
        with self.connect() as conn:
            conn.execute("BEGIN IMMEDIATE")
            count, total = conn.execute("SELECT count(*), coalesce(sum(size + preview_bytes), 0) FROM jobs WHERE expires > ?", (now,)).fetchone()
            if count >= self.settings.music_check_max_jobs or total + size > self.settings.music_check_storage_mb * 1024**2:
                raise HTTPException(429, "Очередь демонстрации заполнена. Попробуйте позже")
            used = {row[0] for row in conn.execute("SELECT code FROM jobs WHERE code IS NOT NULL")}
            free = [str(n) for n in range(10, 100) if str(n) not in used]
            if not free:
                raise HTTPException(429, "Все двузначные номера заняты. Попробуйте позже")
            code = secrets.choice(free)
            conn.execute("INSERT INTO jobs(id,token_hash,name,status,created,expires,size,code) VALUES(?,?,?,'uploading',?,?,?,?)",
                         (job_id, digest(token), name, now, now + self.settings.music_check_ttl_hours * 3600, size, code))
        return job_id, token

    def abort(self, job_id):
        with self.connect() as conn:
            conn.execute("DELETE FROM jobs WHERE id=? AND status='uploading'", (job_id,))
        self.path(job_id).unlink(missing_ok=True)
        self.path(job_id).with_suffix(".partial").unlink(missing_ok=True)

    def row(self, conn, job_id):
        row = conn.execute("SELECT * FROM jobs WHERE id=?", (str(job_id),)).fetchone()
        if row is None:
            raise HTTPException(404, "Задание не найдено")
        if row["expires"] <= time.time():
            raise HTTPException(410, "Срок хранения задания истёк. Загрузите запись заново")
        return row

    def read(self, job_id, token):
        with self.connect() as conn:
            row = self.row(conn, job_id)
            if not hmac.compare_digest(row["token_hash"], digest(token)):
                raise HTTPException(404, "Задание не найдено")
            return self.public(row)

    @staticmethod
    def public(row):
        result = json.loads(row["result"]) if row["result"] else None
        if result:
            previews = json.loads(row["previews"])
            for index, match in enumerate(result["matches"]):
                match["preview_available"] = str(index) in previews
        return dict(id=row["id"], code=row["code"], filename=row["name"], status=row["status"],
                    expires_at=row["expires"], created_at=row["created"], result=result)

    def claim(self, job_id):
        lease = secrets.token_urlsafe(32)
        with self.connect() as conn:
            conn.execute("BEGIN IMMEDIATE")
            if len(job_id) == 2 and job_id.isascii() and job_id.isdigit():
                found = conn.execute("SELECT id FROM jobs WHERE code=? AND expires>?", (job_id, time.time())).fetchone()
                if found is None:
                    raise HTTPException(404, "Задание с таким номером не найдено")
                job_id = found["id"]
            else:
                try:
                    job_id = str(UUID(job_id))
                except ValueError:
                    raise HTTPException(422, "Укажите двузначный номер задания")
            row = self.row(conn, job_id)
            if row["status"] in {"completed", "uploading"}:
                raise HTTPException(409, "Задание завершено или файл ещё загружается")
            if row["status"] == "processing" and row["lease_until"] > time.time():
                raise HTTPException(409, "Задание уже обрабатывается; повторный запуск возможен через час")
            self.clear_previews(row)
            conn.execute("UPDATE jobs SET status='processing', lease_hash=?, lease_until=?, result=NULL, previews='{}', preview_bytes=0 WHERE id=?",
                         (digest(lease), time.time() + LEASE_SECONDS, str(job_id)))
            return dict(id=str(job_id), code=row["code"], filename=row["name"], sha256=row["sha256"],
                        size=row["size"], lease_token=lease, lease_seconds=LEASE_SECONDS)

    def check_lease(self, row, token):
        if (row["status"] != "processing" or not row["lease_hash"]
                or row["lease_until"] <= time.time()
                or not hmac.compare_digest(row["lease_hash"], digest(token))):
            raise HTTPException(409, "Попытка обработки устарела. Получите задание заново")

    def audio(self, job_id, lease):
        with self.connect() as conn:
            row = self.row(conn, job_id)
            self.check_lease(row, lease)
            return self.path(job_id), row["name"]

    def save_preview(self, job_id, lease, index, temporary, size):
        with self.connect() as conn:
            conn.execute("BEGIN IMMEDIATE")
            row = self.row(conn, job_id)
            self.check_lease(row, lease)
            previews = json.loads(row["previews"])
            previous = previews.get(str(index), {}).get("size", 0)
            total = conn.execute("SELECT coalesce(sum(size + preview_bytes), 0) FROM jobs WHERE expires > ?", (time.time(),)).fetchone()[0]
            if total - previous + size > self.settings.music_check_storage_mb * 1024**2:
                raise HTTPException(429, "Недостаточно места для найденного отрывка")
            target = self.root / f"{job_id}.{digest(lease)}.{index}.preview.mp3"
            temporary.replace(target)
            previews[str(index)] = {"file": target.name, "size": size}
            conn.execute("UPDATE jobs SET previews=?, preview_bytes=? WHERE id=?",
                         (json.dumps(previews), row["preview_bytes"] - previous + size, str(job_id)))

    def preview(self, job_id, token, index):
        job = self.read(job_id, token)
        if not job["result"] or job["status"] != "completed" or index >= len(job["result"]["matches"]):
            raise HTTPException(404, "Найденный отрывок недоступен")
        with self.connect() as conn:
            row = self.row(conn, job_id)
            preview = json.loads(row["previews"]).get(str(index))
            if not preview:
                raise HTTPException(404, "Найденный отрывок недоступен")
            return self.root / preview["file"]

    def complete(self, job_id, lease, result):
        with self.connect() as conn:
            conn.execute("BEGIN IMMEDIATE")
            row = self.row(conn, job_id)
            self.check_lease(row, lease)
            if not hmac.compare_digest(result.query_sha256, row["sha256"]):
                raise HTTPException(422, "Результат относится к другому аудиофайлу")
            if result.outcome == "failed":
                self.clear_previews(row)
                conn.execute("UPDATE jobs SET previews='{}', preview_bytes=0 WHERE id=?", (str(job_id),))
            conn.execute("UPDATE jobs SET status=?, result=?, lease_hash=NULL WHERE id=?",
                         (result.outcome, result.model_dump_json(), str(job_id)))
        return {"status": result.outcome}


@router.get("/notebook")
def notebook():
    path = Path(__file__).resolve().parents[1] / "music_plagiarism/colab/CLEWS_site_demo.ipynb"
    return FileResponse(path, filename="CLEWS_site_demo.ipynb", media_type="application/x-ipynb+json",
                        headers={"Cache-Control": "no-store"})


@router.post("/jobs", status_code=201, dependencies=[Depends(enabled)])
async def create_job(request: Request, response: Response,
                     x_file_name: Annotated[str, Header()] = ""):
    # Raw body avoids loading multipart uploads into the API's RAM or /tmp.
    name = unquote(x_file_name).replace("\\", "/").split("/")[-1]
    name = "".join(c for c in name if c.isprintable()).strip()
    if not name or len(name) > 255 or Path(name).suffix.lower() not in ALLOWED_EXTENSIONS:
        raise HTTPException(422, "Выберите MP3, WAV, FLAC, OGG, M4A или AAC")
    maximum = get_settings().music_check_max_upload_mb * 1024**2
    try:
        expected = int(request.headers.get("content-length", "0"))
    except ValueError:
        raise HTTPException(400, "Некорректный размер файла")
    if not 0 < expected <= maximum:
        raise HTTPException(413, f"Размер файла должен быть от 1 байта до {get_settings().music_check_max_upload_mb} МБ")
    store = Store()
    job_id, token = store.reserve(name, expected)
    total, hasher = 0, hashlib.sha256()
    temporary = store.path(job_id).with_suffix(".partial")
    try:
        with temporary.open("xb") as out:
            async for chunk in request.stream():
                total += len(chunk)
                if total > expected or total > maximum:
                    raise HTTPException(413, "Превышен заявленный размер файла")
                out.write(chunk)
                hasher.update(chunk)
        if total != expected:
            raise HTTPException(400, "Файл загружен не полностью")
        temporary.replace(store.path(job_id))
        with store.connect() as conn:
            conn.execute("UPDATE jobs SET status='queued', size=?, sha256=? WHERE id=?", (total, hasher.hexdigest(), job_id))
    except BaseException:
        store.abort(job_id)
        raise
    response.headers["Cache-Control"] = "no-store"
    return {**store.read(job_id, token), "access_token": token}


@router.get("/jobs/{job_id}", dependencies=[Depends(enabled)])
def job_status(job_id: UUID, response: Response,
               x_music_job_token: Annotated[str, Header()] = ""):
    response.headers["Cache-Control"] = "no-store"
    return Store().read(job_id, x_music_job_token)


@router.get("/jobs/{job_id}/audio", dependencies=[Depends(enabled)])
def own_audio(job_id: UUID, x_music_job_token: Annotated[str, Header()] = ""):
    store = Store()
    job = store.read(job_id, x_music_job_token)
    return FileResponse(store.path(job_id), filename=job["filename"], media_type="application/octet-stream",
                        headers={"Cache-Control": "no-store", "X-Content-Type-Options": "nosniff"})


@router.post("/worker/jobs/{job_id}/claim", dependencies=[Depends(worker)])
def claim_job(job_id: str, response: Response):
    response.headers["Cache-Control"] = "no-store"
    return Store().claim(job_id)


@router.get("/worker/jobs/{job_id}/audio", dependencies=[Depends(worker)])
def worker_audio(job_id: UUID, x_claim_token: Annotated[str, Header()] = ""):
    path, name = Store().audio(job_id, x_claim_token)
    return FileResponse(path, filename=name, media_type="application/octet-stream",
                        headers={"Cache-Control": "no-store", "X-Content-Type-Options": "nosniff"})


@router.put("/worker/jobs/{job_id}/result", dependencies=[Depends(worker)])
def upload_result(job_id: UUID, payload: Result,
                  x_claim_token: Annotated[str, Header()] = ""):
    return Store().complete(job_id, x_claim_token, payload)


@router.put("/worker/jobs/{job_id}/matches/{index}/audio", dependencies=[Depends(worker)])
async def upload_preview(job_id: UUID, index: Annotated[int, PathParam(ge=0, lt=MAX_PREVIEWS)],
                         request: Request, x_claim_token: Annotated[str, Header()] = ""):
    store = Store()
    with store.connect() as conn:
        store.check_lease(store.row(conn, job_id), x_claim_token)
    try:
        expected = int(request.headers.get("content-length", "0"))
    except ValueError:
        raise HTTPException(400, "Некорректный размер отрывка")
    if not 0 < expected <= MAX_PREVIEW_BYTES:
        raise HTTPException(413, "Отрывок должен быть не больше 256 КиБ")
    if request.headers.get("content-type", "").split(";")[0] != "audio/mpeg":
        raise HTTPException(415, "Нужен MP3-отрывок")
    temporary = store.root / f"{job_id}.{uuid4()}.partial"
    received = 0
    try:
        with temporary.open("xb") as out:
            async for chunk in request.stream():
                received += len(chunk)
                if received > expected:
                    raise HTTPException(413, "Превышен заявленный размер отрывка")
                out.write(chunk)
        if received != expected:
            raise HTTPException(400, "Отрывок загружен не полностью")
        with temporary.open("rb") as stream:
            signature = stream.read(3)
        if not (signature == b"ID3" or len(signature) >= 2 and signature[0] == 255 and signature[1] & 224 == 224):
            raise HTTPException(415, "Нужен MP3-отрывок")
        store.save_preview(job_id, x_claim_token, index, temporary, received)
    finally:
        temporary.unlink(missing_ok=True)
    return {"status": "uploaded"}


@router.get("/jobs/{job_id}/matches/{index}/audio", dependencies=[Depends(enabled)])
def match_audio(job_id: UUID, index: Annotated[int, PathParam(ge=0, lt=MAX_PREVIEWS)],
                x_music_job_token: Annotated[str, Header()] = ""):
    path = Store().preview(job_id, x_music_job_token, index)
    return FileResponse(path, filename=f"match-{index + 1}.mp3", media_type="audio/mpeg",
                        headers={"Cache-Control": "no-store", "X-Content-Type-Options": "nosniff"})
