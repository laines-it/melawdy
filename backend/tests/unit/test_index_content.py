import json
import math
import os
from pathlib import Path
import subprocess
import sys
from types import SimpleNamespace
from unittest.mock import Mock

import pytest
from sqlalchemy.orm import Session

from ml import index_content
from ml.constants import EMBEDDING_DIMENSIONS, EMBEDDING_MAX_TOKENS, PASSAGE_PREFIX
from ml.embeddings import LegalEmbedder


def vector(index=0):
    return [1.0 if position == index else 0.0 for position in range(EMBEDDING_DIMENSIONS)]


def character_model():
    model = Mock()
    model.get_sentence_embedding_dimension.return_value = EMBEDDING_DIMENSIONS
    model.tokenizer.side_effect = lambda texts, **kwargs: {
        "input_ids": [[1] * (len(text) + 2) for text in texts],
    }
    model.encode.side_effect = lambda texts, **kwargs: [
        vector(0 if text.removeprefix(PASSAGE_PREFIX).startswith("A") else 1) for text in texts
    ]
    return model


@pytest.mark.parametrize("text", [
    "A" * 501, "A" * 502, "A" * 1445,
    ("Первое предложение. Второе предложение!\n\n" * 80).strip(),
    "НепрерывныйТекстБезПробелов" * 100,
])
def test_long_document_split_keeps_all_text_and_respects_prefix_budget(text):
    model = character_model()
    embedder = LegalEmbedder(model)
    parts = embedder.split_document(text)
    assert "".join(parts) == text
    assert all(part.strip() for part in parts)
    result = embedder.encode_documents([text])
    assert len(result) == 1 and len(result[0]) == EMBEDDING_DIMENSIONS
    assert math.hypot(*result[0]) == pytest.approx(1)
    encoded = model.encode.call_args.args[0]
    assert len(encoded) == len(parts)
    assert all(len(part) + 2 <= EMBEDDING_MAX_TOKENS for part in encoded)


def test_long_document_uses_token_weighted_pooling_and_preserves_batch_order():
    model = character_model()
    result = LegalEmbedder(model).encode_documents(["A" * 501 + "B" * 199, "BBBB"])
    norm = math.hypot(501, 199)
    assert result[0][:2] == pytest.approx([501 / norm, 199 / norm])
    assert result[1] == vector(1)


def indexing_runtime(monkeypatch, batches, *, missing=0, changed=False, force=False):
    pages = iter(batches)
    session = Mock(spec=Session)
    statements = []

    def execute(statement):
        statements.append(statement)
        if statement.is_select:
            return SimpleNamespace(all=lambda: next(pages, []))
        return SimpleNamespace(rowcount=0 if changed else 1)

    session.execute.side_effect = execute
    session.scalar.return_value = missing
    context = Mock(__enter__=Mock(return_value=session), __exit__=Mock(return_value=False))
    monkeypatch.setattr(index_content, "SessionLocal", lambda: context)
    embedder = Mock()
    embedder.encode_documents.side_effect = lambda texts: [vector() for _ in texts]
    factory = Mock(return_value=embedder)
    monkeypatch.setattr(index_content, "get_embedder", factory)
    monkeypatch.setattr(sys, "argv", ["index_content", "--batch-size", "2"] + (["--force"] if force else []))
    return session, factory, embedder, statements


def test_completed_index_does_not_load_model_or_write_again(monkeypatch, capsys):
    session, factory, embedder, statements = indexing_runtime(monkeypatch, [])
    index_content.main()
    factory.assert_not_called()
    embedder.encode_documents.assert_not_called()
    session.commit.assert_not_called()
    assert all(statement.is_select for statement in statements)
    assert "embedding IS NULL" in str(statements[0])
    assert "Index ready: 0 chunks calculated" in capsys.readouterr().out


def test_batches_reuse_model_and_guard_concurrent_body_changes(monkeypatch):
    rows = [SimpleNamespace(id=index, body=f"Текст {index}", updated_at="revision") for index in [1, 2, 3]]
    session, factory, embedder, statements = indexing_runtime(monkeypatch, [rows[:2], rows[2:]])
    index_content.main()
    assert factory.call_count == 1
    assert embedder.encode_documents.call_count == 2
    assert session.commit.call_count == 2
    writes = [statement for statement in statements if statement.is_update]
    assert len(writes) == 3
    for statement, row in zip(writes, rows, strict=True):
        assert "content_item_chunks.updated_at =" in str(statement)
        assert "content_item_chunks.body =" in str(statement)
        assert statement.compile().params["body_1"] == row.body
        assert statement.compile().params["embedding"] == vector()


def test_indexing_failure_does_not_write_incomplete_batch(monkeypatch):
    row = SimpleNamespace(id=1, body="Текст", updated_at="revision")
    session, factory, embedder, statements = indexing_runtime(monkeypatch, [[row]])
    embedder.encode_documents.side_effect = RuntimeError("model failed")
    with pytest.raises(RuntimeError, match="model failed"):
        index_content.main()
    assert all(statement.is_select for statement in statements)
    session.commit.assert_not_called()


def test_missing_vectors_after_concurrent_edits_fail_startup(monkeypatch):
    row = SimpleNamespace(id=1, body="Текст", updated_at="revision")
    indexing_runtime(monkeypatch, [[row]], changed=True, missing=1)
    with pytest.raises(RuntimeError, match="1 chunks still lack embeddings"):
        index_content.main()


def test_force_recomputes_existing_vectors(monkeypatch):
    row = SimpleNamespace(id=1, body="Текст", updated_at="revision")
    session, factory, embedder, statements = indexing_runtime(monkeypatch, [[row]], force=True)
    index_content.main()
    assert "embedding IS NULL" not in str(statements[0])
    assert len([statement for statement in statements if statement.is_update]) == 1


@pytest.mark.parametrize("fail_index", ["none", "legacy", "search", "disabled"])
def test_real_entrypoint_indexes_after_migration_and_before_server(tmp_path, fail_index):
    binaries = tmp_path / "bin"
    binaries.mkdir()
    log = tmp_path / "startup.jsonl"
    executable = '''#!/usr/bin/env python3
import json, os, sys
from pathlib import Path
name = Path(sys.argv[0]).name
if name == "python" and sys.argv[1] == "-c":
    print("0" if os.environ["FAIL_INDEX"] == "disabled" else "1")
    sys.exit(0)
with open(os.environ["STARTUP_LOG"], "a") as log:
    log.write(json.dumps([name, *sys.argv[1:]]) + "\\n")
if name == "python" and ((sys.argv[1:] == ["-m", "ml.index_content"] and os.environ["FAIL_INDEX"] == "legacy") or (sys.argv[1:] == ["-m", "ml.index_search_content"] and os.environ["FAIL_INDEX"] == "search")):
    sys.exit(23)
'''
    for name in ["alembic", "python", "uvicorn"]:
        command = binaries / name
        command.write_text(executable)
        command.chmod(0o755)
    env = {**os.environ, "PATH": str(binaries) + os.pathsep + os.environ["PATH"],
           "STARTUP_LOG": str(log), "FAIL_INDEX": fail_index}
    script = Path(__file__).resolve().parents[2] / "entrypoint.sh"
    result = subprocess.run(["sh", str(script)], env=env, capture_output=True, timeout=10)
    calls = [json.loads(line) for line in log.read_text().splitlines()]
    if fail_index == "disabled":
        assert result.returncode == 0
        assert calls == [["alembic", "upgrade", "head"],
                         ["python", "-m", "backend.manage_admin", "--from-env"],
                         ["uvicorn", "backend.main:app", "--host", "0.0.0.0", "--port", "8000"]]
        return
    assert calls[:3] == [["alembic", "upgrade", "head"], ["python", "-m", "backend.manage_admin", "--from-env"],
                         ["python", "-m", "ml.index_content"]]
    if fail_index != "none":
        assert result.returncode == 23
        assert len(calls) == (3 if fail_index == "legacy" else 4)
    else:
        assert result.returncode == 0, result.stderr.decode()
        assert calls[3] == ["python", "-m", "ml.index_search_content"]
        assert calls[4] == ["uvicorn", "backend.main:app", "--host", "0.0.0.0", "--port", "8000"]
