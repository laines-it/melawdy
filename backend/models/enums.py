from enum import Enum

from sqlalchemy import Enum as SAEnum


class UserType(str, Enum):
    INDIVIDUAL = "individual"
    ORGANIZATION = "organization"
    LAWYER = "lawyer"
    ADMIN = "admin"


class ContentType(str, Enum):
    ARTICLE = "article"
    GUIDE = "guide"
    FAQ = "faq"
    NEWS = "news"


class ContentStatus(str, Enum):
    DRAFT = "draft"
    PUBLISHED = "published"
    ARCHIVED = "archived"


class QuestionType(str, Enum):
    SINGLE_CHOICE = "single_choice"
    MULTIPLE_CHOICE = "multiple_choice"
    TEXT = "text"
    BOOLEAN = "boolean"


class DocumentType(str, Enum):
    CONTRACT = "contract"
    CLAIM = "claim"
    APPLICATION = "application"
    OTHER = "other"


class DocumentStatus(str, Enum):
    DRAFT = "draft"
    IN_PROGRESS = "in_progress"
    COMPLETED = "completed"
    ARCHIVED = "archived"


class DeadlineStatus(str, Enum):
    NONE = "none"
    UPCOMING = "upcoming"
    OVERDUE = "overdue"
    COMPLETED = "completed"


def enum_type(enum_class: type[Enum], name: str) -> SAEnum:
    """Store public values rather than Python enum member names."""
    return SAEnum(
        enum_class, name=name, values_callable=lambda cls: [item.value for item in cls],
        validate_strings=True,
    )
