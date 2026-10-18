from dataclasses import dataclass

from pydantic import BaseModel

from backend import admin_schemas as schemas
from backend.models import (
    ApplicationType, AssessmentOption, AssessmentQuestion, AssessmentResult, AssessmentResultRule,
    AssessmentSurvey, Base, ContentCategory, ContentItem, ContentItemChunk, ContentItemTag,
    ContentTag, DocumentTemplate, FeeRate, GlossaryTerm, GlossaryTermContent, MktuClass, QAPair,
)


@dataclass(frozen=True)
class Resource:
    key: str
    title: str
    model: type[Base]
    schema: type[BaseModel]
    label_field: str


RESOURCES = {resource.key: resource for resource in [
    Resource("articles", "Статьи и материалы", ContentItem, schemas.ArticleInput, "title"),
    Resource("categories", "Категории", ContentCategory, schemas.CategoryInput, "name"),
    Resource("tags", "Теги", ContentTag, schemas.TagInput, "name"),
    Resource("article-tags", "Теги статей", ContentItemTag, schemas.ArticleTagInput, "content_item_id"),
    Resource("chunks", "Разделы статей (чанки)", ContentItemChunk, schemas.ChunkInput, "body"),
    Resource("glossary", "Термины", GlossaryTerm, schemas.GlossaryInput, "term"),
    Resource("glossary-content", "Термины в статьях", GlossaryTermContent, schemas.GlossaryLinkInput, "term_id"),
    Resource("qa", "Вопросы и ответы", QAPair, schemas.QAPairInput, "question"),
    Resource("surveys", "Assessment: опросы", AssessmentSurvey, schemas.SurveyInput, "title"),
    Resource("questions", "Assessment: вопросы", AssessmentQuestion, schemas.QuestionInput, "text"),
    Resource("options", "Assessment: варианты ответов", AssessmentOption, schemas.OptionInput, "text"),
    Resource("assessment-results", "Assessment: результаты", AssessmentResult, schemas.ResultInput, "title"),
    Resource("assessment-rules", "Assessment: правила", AssessmentResultRule, schemas.RuleInput, "survey_id"),
    Resource("templates", "Шаблоны документов", DocumentTemplate, schemas.TemplateInput, "title"),
    Resource("application-types", "Типы заявок", ApplicationType, schemas.ApplicationTypeInput, "name"),
    Resource("mktu-classes", "Классы МКТУ", MktuClass, schemas.MktuInput, "title"),
    Resource("fee-rates", "Ставки пошлин", FeeRate, schemas.FeeRateInput, "legal_basis"),
]}

LABELS = {
    "title": "Название", "name": "Название", "slug": "Slug (уникальное имя в URL)",
    "type": "Тип материала", "status": "Статус", "category_id": "Категория",
    "parent_id": "Родительская категория", "sort_order": "Порядок сортировки",
    "summary": "Краткое описание", "published_at": "Дата публикации",
    "chunks": "Текстовые разделы статьи", "content_item_id": "Статья", "tag_id": "Тег",
    "chunk_index": "Номер раздела (с нуля)", "body": "Текст", "term": "Термин",
    "definition": "Краткое определение", "full_definition": "Полное определение",
    "term_id": "Термин", "question": "Вопрос", "answer": "Ответ", "version": "Версия",
    "is_active": "Активен", "survey_id": "Опрос", "text": "Текст",
    "question_type": "Тип вопроса", "is_required": "Обязательный вопрос",
    "question_id": "Вопрос", "value": "Значение ответа", "code": "Уникальный код",
    "description": "Описание", "recommended_content_id": "Рекомендованная статья",
    "recommended_document_template_id": "Рекомендованный шаблон", "result_id": "Результат",
    "condition_json": "Условие (JSON)", "priority": "Приоритет",
    "document_type": "Тип документа", "file_path": "Ключ файла в MinIO (необязательно)",
    "schema_json": "Разделы и поля конструктора (JSON)", "structure_json": "Блоки документа (JSON)",
    "class_number": "Номер класса МКТУ", "application_type_id": "Тип заявки",
    "mktu_class_id": "Класс МКТУ", "is_urgent": "Срочно", "amount": "Сумма",
    "currency": "Валюта", "valid_from": "Действует с", "valid_to": "Действует до",
    "legal_basis": "Правовое основание",
}

FOREIGN_RESOURCES = {
    "category_id": "categories", "parent_id": "categories", "content_item_id": "articles",
    "tag_id": "tags", "term_id": "glossary", "survey_id": "surveys", "question_id": "questions",
    "recommended_content_id": "articles", "recommended_document_template_id": "templates",
    "result_id": "assessment-results", "application_type_id": "application-types",
    "mktu_class_id": "mktu-classes",
}


def metadata(resource: Resource) -> dict:
    document = resource.schema.model_json_schema()
    fields = []
    for name, definition in document["properties"].items():
        variants = definition.get("anyOf", [definition])
        nullable = any(item.get("type") == "null" for item in variants)
        value = next(item for item in variants if item.get("type") != "null")
        if "$ref" in value:
            value = document["$defs"][value["$ref"].split("/")[-1]]
        kind = "text"
        if name in FOREIGN_RESOURCES:
            kind = "foreign"
        elif "enum" in value:
            kind = "enum"
        elif value.get("type") == "boolean":
            kind = "boolean"
        elif value.get("type") == "integer":
            kind = "number"
        elif name == "amount":
            kind = "decimal"
        elif value.get("type") == "object":
            kind = "json"
        elif name == "chunks":
            kind = "texts"
        elif value.get("format") == "date-time":
            kind = "datetime-local"
        elif value.get("format") == "date":
            kind = "date"
        elif name in {"body", "text", "summary", "description", "definition", "full_definition",
                       "question", "answer", "legal_basis"}:
            kind = "textarea"
        fields.append({"name": name, "label": LABELS.get(name, name), "kind": kind,
                       "required": name in document.get("required", []), "nullable": nullable,
                       "default": definition.get("default"), "choices": value.get("enum", []),
                       "max_length": value.get("maxLength"), "minimum": value.get("minimum"),
                       "maximum": value.get("maximum"), "resource": FOREIGN_RESOURCES.get(name)})
    return {"key": resource.key, "title": resource.title, "fields": fields}
