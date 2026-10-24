from types import SimpleNamespace
from unittest.mock import Mock

import pytest
from sqlalchemy.orm import Session

from ml import index_search_content as indexing
from ml.constants import EMBEDDING_DIMENSIONS


def runtime(monkeypatch, *, ready=False, changed=False, matching=False):
    source = indexing.ArticleSource(7, "Защита записи", ("Сохраните оригинал записи, чтобы подтвердить авторство.",))
    read = Mock(spec=Session)
    fingerprint = source.fingerprint if ready or matching else "outdated"
    read.execute.return_value.all.return_value = [(source.id, fingerprint)]
    write = Mock(spec=Session)
    write.scalar.return_value = SimpleNamespace(title="Изменено" if changed else source.title)
    write.scalars.return_value = source.bodies
    final = Mock(spec=Session)
    final.execute.return_value.all.return_value = [(source.id, source.fingerprint)]
    sessions = iter([read, final] if ready else [read, write, final])

    def factory():
        session = next(sessions)
        return Mock(__enter__=Mock(return_value=session), __exit__=Mock(return_value=False))

    monkeypatch.setattr(indexing, "read_sources", lambda session: [source])
    embedder = Mock()
    embedder.split_document.side_effect = lambda body, context: [context + body]
    embedder.encode_documents.side_effect = lambda bodies: [[1.0] + [0.0] * (EMBEDDING_DIMENSIONS - 1) for _ in bodies]
    provider = Mock(return_value=embedder)
    return source, factory, provider, write


def test_unchanged_sources_skip_model_and_writes(monkeypatch):
    _, factory, provider, write = runtime(monkeypatch, ready=True)
    assert indexing.index_articles(factory, provider) == 0
    provider.assert_not_called()
    write.execute.assert_not_called()


def test_new_fragments_are_saved_together_with_their_fingerprint(monkeypatch):
    source, factory, provider, write = runtime(monkeypatch)
    assert indexing.index_articles(factory, provider, batch_size=2) == 1
    provider.assert_called_once_with()
    assert write.add.call_args.args[0].source_hash == source.fingerprint
    fragments = write.add_all.call_args.args[0]
    assert len(fragments) == 1
    assert fragments[0].body.startswith(source.title + "\n\n")
    assert fragments[0].content_item_id == source.id
    write.commit.assert_called_once_with()


def test_encoding_failure_preserves_the_previous_index(monkeypatch):
    _, factory, provider, write = runtime(monkeypatch)
    provider.return_value.encode_documents.side_effect = RuntimeError("inference failed")
    with pytest.raises(RuntimeError, match="inference failed"):
        indexing.index_articles(factory, provider)
    write.execute.assert_not_called()
    write.commit.assert_not_called()


def test_concurrent_edit_preserves_the_previous_index_and_blocks_startup(monkeypatch):
    _, factory, provider, write = runtime(monkeypatch, changed=True)
    with pytest.raises(RuntimeError, match="changed during indexing"):
        indexing.index_articles(factory, provider)
    write.execute.assert_not_called()
    write.commit.assert_not_called()


def test_force_rebuilds_an_existing_index(monkeypatch):
    source, factory, provider, write = runtime(monkeypatch, matching=True)
    assert indexing.index_articles(factory, provider, force=True) == 1
    write.commit.assert_called_once_with()


def test_missing_index_after_concurrent_change_fails_readiness(monkeypatch):
    _, factory, provider, write = runtime(monkeypatch)
    original = indexing.read_sources
    calls = iter([original(None), [indexing.ArticleSource(7, "Новый заголовок", ("Новый текст",))]])
    monkeypatch.setattr(indexing, "read_sources", lambda session: next(calls))
    with pytest.raises(RuntimeError, match="Search index changed"):
        indexing.index_articles(factory, provider)
