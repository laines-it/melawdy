"""
Заполнить content_items.slug для статей с пустым slug.

Колонка slug уже создана в 0002_domain_schema (nullable=False, UNIQUE).
Здесь только бэкфилл: пустая строка '' трактуется как «slug не задан».
Числовой суффикс (-<id>, -<id>-2, ...) гарантирует уникальность в рамках UNIQUE(slug).
"""
from alembic import op
import sqlalchemy as sa

revision = "0010_backfill_content_item_slugs"
down_revision = "0009_fee_procedures"
branch_labels = None
depends_on = None


def upgrade() -> None:
    bind = op.get_bind()

    # Транслитерация RU→LAT + ASCII-нормализация. Дублируем в SQL, чтобы
    # не тянуть Python-код в миграцию: миграция должна быть самодостаточной.
    op.execute(sa.text("""
        CREATE OR REPLACE FUNCTION pg_temp.melawdy_slugify(input text, fallback_id bigint)
        RETURNS text
        LANGUAGE plpgsql
        AS $$
        DECLARE
            s text;
            out text := '';
            ch text;
            i int;
        BEGIN
            s := lower(coalesce(input, ''));

            -- простая транслитерация посимвольно
            FOR i IN 1..char_length(s) LOOP
                ch := substr(s, i, 1);
                out := out || CASE ch
                    WHEN 'а' THEN 'a'  WHEN 'б' THEN 'b'  WHEN 'в' THEN 'v'
                    WHEN 'г' THEN 'g'  WHEN 'д' THEN 'd'  WHEN 'е' THEN 'e'
                    WHEN 'ё' THEN 'e'  WHEN 'ж' THEN 'zh' WHEN 'з' THEN 'z'
                    WHEN 'и' THEN 'i'  WHEN 'й' THEN 'y'  WHEN 'к' THEN 'k'
                    WHEN 'л' THEN 'l'  WHEN 'м' THEN 'm'  WHEN 'н' THEN 'n'
                    WHEN 'о' THEN 'o'  WHEN 'п' THEN 'p'  WHEN 'р' THEN 'r'
                    WHEN 'с' THEN 's'  WHEN 'т' THEN 't'  WHEN 'у' THEN 'u'
                    WHEN 'ф' THEN 'f'  WHEN 'х' THEN 'h'  WHEN 'ц' THEN 'ts'
                    WHEN 'ч' THEN 'ch' WHEN 'ш' THEN 'sh' WHEN 'щ' THEN 'sch'
                    WHEN 'ъ' THEN ''   WHEN 'ы' THEN 'y'  WHEN 'ь' THEN ''
                    WHEN 'э' THEN 'e'  WHEN 'ю' THEN 'yu' WHEN 'я' THEN 'ya'
                    ELSE ch
                END;
            END LOOP;

            -- всё, что не [a-z0-9_-], заменяем на '-'
            out := regexp_replace(out, '[^a-z0-9_-]+', '-', 'g');
            -- схлопываем повторные '-'
            out := regexp_replace(out, '-+', '-', 'g');
            -- обрезаем до 200 и убираем ведущие/хвостовые '-_'
            out := btrim(substr(out, 1, 200), '-_');

            IF out = '' THEN
                out := 'article-' || fallback_id::text;
            END IF;

            RETURN out;
        END;
        $$;
    """))

    # 1) Базовый slug для всех, у кого он пуст
    op.execute(sa.text("""
        UPDATE content_items
        SET slug = pg_temp.melawdy_slugify(title, id)
        WHERE slug IS NULL OR slug = '';
    """))

    # 2) Разрешаем коллизии: если два одинаковых базовых slug, добавляем -<id>
    op.execute(sa.text("""
        WITH dup AS (
            SELECT slug
            FROM content_items
            GROUP BY slug
            HAVING count(*) > 1
        )
        UPDATE content_items ci
        SET slug = ci.slug || '-' || ci.id::text
        FROM dup
        WHERE ci.slug = dup.slug;
    """))

    # 3) Если и после этого есть коллизии — добиваем -<id>-2, -<id>-3, ...
    op.execute(sa.text("""
        DO $$
        DECLARE
            r record;
            candidate text;
            suffix int;
        BEGIN
            FOR r IN
                SELECT id, slug FROM content_items
                WHERE slug IN (
                    SELECT slug FROM content_items GROUP BY slug HAVING count(*) > 1
                )
                ORDER BY id
            LOOP
                candidate := r.slug;
                suffix := 2;
                WHILE EXISTS (SELECT 1 FROM content_items WHERE slug = candidate AND id <> r.id) LOOP
                    candidate := r.slug || '-' || suffix::text;
                    suffix := suffix + 1;
                END LOOP;
                UPDATE content_items SET slug = candidate WHERE id = r.id;
            END LOOP;
        END $$;
    """))

    # 4) Страховка: NULL больше не должно быть
    remaining = bind.execute(sa.text(
        "SELECT count(*) FROM content_items WHERE slug IS NULL OR slug = ''"
    )).scalar_one()
    if remaining:
        raise RuntimeError(f"После бэкфилла осталось {remaining} статей без slug")


def downgrade() -> None:
    # Данные бизнес-уровня не откатываем: слаг — часть идентичности статьи.
    pass
