"""Import a document template without overwriting an existing template's slug."""

import argparse
import json
from pathlib import Path
from typing import Any

from pydantic import ValidationError
from sqlalchemy import select
from sqlalchemy.dialects.postgresql import insert
from sqlalchemy.exc import SQLAlchemyError
from sqlalchemy.orm import Session

from backend.admin_schemas import TemplateInput
from backend.db import SessionLocal
from backend.models import DocumentTemplate

DEFAULT_TEMPLATE = Path(__file__).resolve().parents[1] / "docs/examples/coauthors-template.json"


def import_template(session: Session, source: dict[str, Any]) -> dict[str, Any]:
    payload = TemplateInput.model_validate(source).model_dump(by_alias=True)
    inserted_id = session.scalar(
        insert(DocumentTemplate).values(**payload)
        .on_conflict_do_nothing(index_elements=[DocumentTemplate.slug])
        .returning(DocumentTemplate.id)
    )
    template = session.scalar(select(DocumentTemplate).where(DocumentTemplate.slug == payload["slug"]))
    if template is None:
        raise RuntimeError("Не удалось прочитать импортированный шаблон")
    return {
        "created": inserted_id is not None,
        "id": str(template.id),
        "title": template.title,
        "slug": template.slug,
        "active": template.is_active,
        "sections": len((template.schema_json or {}).get("sections", [])),
        "blocks": len((template.structure_json or {}).get("blocks", [])),
    }


def main() -> None:
    parser = argparse.ArgumentParser(
        description="Добавить шаблон документа из JSON. Существующий slug остаётся без изменений.",
    )
    parser.add_argument("file", nargs="?", type=Path, default=DEFAULT_TEMPLATE,
                        help="JSON шаблона (по умолчанию — пример соглашения соавторов)")
    args = parser.parse_args()
    try:
        source = json.loads(args.file.read_text(encoding="utf-8-sig"))
        # Validate before opening a transaction, including when the database is unavailable.
        TemplateInput.model_validate(source)
    except (OSError, UnicodeError, ValueError, ValidationError) as error:
        parser.error(f"Не удалось прочитать шаблон: {error}")
    try:
        with SessionLocal.begin() as session:
            result = import_template(session, source)
    except SQLAlchemyError as error:
        parser.exit(1, f"Ошибка БД ({type(error).__name__}). Проверьте подключение POSTGRES_*, "
                    "доступность PostgreSQL и применение миграций.\n")
    print(json.dumps(result, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
