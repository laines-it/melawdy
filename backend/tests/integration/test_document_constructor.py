"""Тест генерации DOCX из structure_json."""

from pathlib import Path

from backend.cabinet import render_structure, text_to_docx


def test_generate_docx_from_structure():
    """Берём структуру, подставляем параметры, получаем DOCX."""

    structure = {
        "blocks": [
            {
                "id": "title",
                "template": "СОГЛАШЕНИЕ СОАВТОРОВ\n\nг. {{city}}",
            },
            {
                "id": "parties",
                "template": "{{author1}} и {{author2}} заключили соглашение.",
            },
            {
                "id": "exclusive",
                "when": "license_kind == exclusive",
                "template": "Лицензия ИСКЛЮЧИТЕЛЬНАЯ.",
            },
            {
                "id": "simple",
                "when": "license_kind == non_exclusive",
                "template": "Лицензия НЕИСКЛЮЧИТЕЛЬНАЯ.",
            },
        ]
    }

    params = {
        "city": "Москва",
        "author1": "Иванов И.И.",
        "author2": "Петров П.П.",
        "license_kind": "exclusive",
    }

    # 1. Рендерим текст
    text = render_structure(structure, params)
    print("\n=== Сгенерированный текст ===")
    print(text)

    # 2. Проверяем подстановку
    assert "Москва" in text
    assert "Иванов И.И." in text
    assert "Петров П.П." in text
    assert "ИСКЛЮЧИТЕЛЬНАЯ" in text
    assert "НЕИСКЛЮЧИТЕЛЬНАЯ" not in text  # не должно попасть

    # 3. Генерируем DOCX
    docx_bytes = text_to_docx(text)

    # 4. Сохраняем в файл для проверки
    output_path = Path("test_output.docx")
    output_path.write_bytes(docx_bytes)
    print(f"\n✅ Файл сохранён: {output_path.absolute()}")

    assert len(docx_bytes) > 0