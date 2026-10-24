"""Import or update the fee calculator tree from JSON."""
import argparse
import json
from pathlib import Path

from sqlalchemy.dialects.postgresql import insert
from sqlalchemy.orm import Session

from backend.db import SessionLocal
from backend.models import ApplicationType, FeeCatalog

DEFAULT_SOURCE = Path(__file__).resolve().parents[1] / "docs/examples/Выбор_процедуры_Xmind.json"
CATALOG_CODE = "procedures"


def import_fees(session: Session, source: dict) -> dict:
    entries = source["procedures"] + source["service_selection"]["options"]
    for entry in entries:
        statement = insert(ApplicationType).values(code=entry["id"], name=entry["name"])
        session.execute(statement.on_conflict_do_update(
            index_elements=[ApplicationType.code], set_={"name": statement.excluded.name},
        ))
    statement = insert(FeeCatalog).values(code=CATALOG_CODE, source_json=source)
    session.execute(statement.on_conflict_do_update(
        index_elements=[FeeCatalog.code], set_={"source_json": statement.excluded.source_json},
    ))
    return {"catalog": CATALOG_CODE, "procedures": len(entries)}


def main() -> None:
    parser = argparse.ArgumentParser(description="Загрузить дерево калькулятора пошлин из JSON в БД.")
    parser.add_argument("file", nargs="?", type=Path, default=DEFAULT_SOURCE)
    args = parser.parse_args()
    source = json.loads(args.file.read_text(encoding="utf-8-sig"))
    with SessionLocal.begin() as session:
        result = import_fees(session, source)
    print(json.dumps(result, ensure_ascii=False))


if __name__ == "__main__":
    main()
