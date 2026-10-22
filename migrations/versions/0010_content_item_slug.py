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

    # Resolve collisions before writing into the existing unique slug column.
    op.execute(sa.text("""
        DO $$
        DECLARE
            r record;
            base text;
            candidate text;
            suffix int;
        BEGIN
            FOR r IN SELECT id, title FROM content_items
                     WHERE slug IS NULL OR slug = '' ORDER BY id FOR UPDATE
            LOOP
                base := pg_temp.melawdy_slugify(r.title, r.id);
                candidate := base;
                suffix := 0;
                WHILE EXISTS (SELECT 1 FROM content_items WHERE slug = candidate AND id <> r.id) LOOP
                    suffix := suffix + 1;
                    candidate := base || '-' || r.id::text
                                 || CASE WHEN suffix = 1 THEN '' ELSE '-' || suffix::text END;
                END LOOP;
                UPDATE content_items SET slug = candidate WHERE id = r.id;
            END LOOP;
        END $$;
    """))


def downgrade() -> None:
    # Данные бизнес-уровня не откатываем: слаг — часть идентичности статьи.
    pass
