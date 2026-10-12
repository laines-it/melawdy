"""Add the approved MeLawDy domain schema without deleting legacy documents."""
from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql
import pgvector.sqlalchemy

revision = "0002_domain_schema"
down_revision = "0001_initial"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.execute("CREATE TYPE content_status AS ENUM ('draft', 'published', 'archived')")
    op.execute("CREATE TYPE content_type AS ENUM ('article', 'guide', 'faq', 'news')")
    op.execute("CREATE TYPE deadline_status AS ENUM ('none', 'upcoming', 'overdue', 'completed')")
    op.execute("CREATE TYPE document_status AS ENUM ('draft', 'in_progress', 'completed', 'archived')")
    op.execute("CREATE TYPE document_type AS ENUM ('contract', 'claim', 'application', 'other')")
    op.execute("CREATE TYPE question_type AS ENUM ('single_choice', 'multiple_choice', 'text', 'boolean')")
    op.execute("CREATE TYPE user_type AS ENUM ('individual', 'organization', 'lawyer', 'admin')")
    op.create_table('application_types',
    sa.Column('code', sa.String(length=100), nullable=False),
    sa.Column('name', sa.String(length=255), nullable=False),
    sa.Column('description', sa.Text(), nullable=True),
    sa.Column('id', sa.BigInteger(), sa.Identity(always=False), nullable=False),
    sa.PrimaryKeyConstraint('id', name=op.f('pk_application_types')),
    sa.UniqueConstraint('code', name=op.f('uq_application_types_code'))
    )
    op.create_table('assessment_surveys',
    sa.Column('title', sa.String(length=500), nullable=False),
    sa.Column('version', sa.Integer(), server_default=sa.text('1'), nullable=False),
    sa.Column('is_active', sa.Boolean(), server_default=sa.text('true'), nullable=False),
    sa.Column('id', sa.BigInteger(), sa.Identity(always=False), nullable=False),
    sa.Column('created_at', sa.DateTime(timezone=True), server_default=sa.text('now()'), nullable=False),
    sa.CheckConstraint('version > 0', name=op.f('ck_assessment_surveys_positive_version')),
    sa.PrimaryKeyConstraint('id', name=op.f('pk_assessment_surveys'))
    )
    op.create_table('content_categories',
    sa.Column('parent_id', sa.BigInteger(), nullable=True),
    sa.Column('name', sa.String(length=255), nullable=False),
    sa.Column('slug', sa.String(length=255), nullable=False),
    sa.Column('sort_order', sa.Integer(), server_default=sa.text('0'), nullable=False),
    sa.Column('id', sa.BigInteger(), sa.Identity(always=False), nullable=False),
    sa.CheckConstraint('parent_id IS NULL OR parent_id <> id', name=op.f('ck_content_categories_not_own_parent')),
    sa.CheckConstraint('sort_order >= 0', name=op.f('ck_content_categories_sort_order_nonnegative')),
    sa.ForeignKeyConstraint(['parent_id'], ['content_categories.id'], name=op.f('fk_content_categories_parent_id_content_categories'), ondelete='RESTRICT'),
    sa.PrimaryKeyConstraint('id', name=op.f('pk_content_categories')),
    sa.UniqueConstraint('slug', name=op.f('uq_content_categories_slug'))
    )
    op.create_index(op.f('ix_content_categories_parent_id'), 'content_categories', ['parent_id'], unique=False)
    op.create_table('content_tags',
    sa.Column('name', sa.String(length=255), nullable=False),
    sa.Column('slug', sa.String(length=255), nullable=False),
    sa.Column('id', sa.BigInteger(), sa.Identity(always=False), nullable=False),
    sa.PrimaryKeyConstraint('id', name=op.f('pk_content_tags')),
    sa.UniqueConstraint('name', name=op.f('uq_content_tags_name')),
    sa.UniqueConstraint('slug', name=op.f('uq_content_tags_slug'))
    )
    op.create_table('document_templates',
    sa.Column('document_type', postgresql.ENUM('contract', 'claim', 'application', 'other', name='document_type', create_type=False), nullable=False),
    sa.Column('title', sa.String(length=500), nullable=False),
    sa.Column('slug', sa.String(length=255), nullable=False),
    sa.Column('description', sa.Text(), nullable=True),
    sa.Column('body', sa.Text(), nullable=False),
    sa.Column('file_path', sa.String(length=1024), nullable=True),
    sa.Column('is_active', sa.Boolean(), server_default=sa.text('true'), nullable=False),
    sa.Column('id', sa.BigInteger(), sa.Identity(always=False), nullable=False),
    sa.Column('created_at', sa.DateTime(timezone=True), server_default=sa.text('now()'), nullable=False),
    sa.Column('updated_at', sa.DateTime(timezone=True), server_default=sa.text('now()'), nullable=False),
    sa.PrimaryKeyConstraint('id', name=op.f('pk_document_templates')),
    sa.UniqueConstraint('slug', name=op.f('uq_document_templates_slug'))
    )
    op.create_table('glossary_terms',
    sa.Column('term', sa.String(length=255), nullable=False),
    sa.Column('definition', sa.Text(), nullable=False),
    sa.Column('full_definition', sa.Text(), nullable=True),
    sa.Column('id', sa.BigInteger(), sa.Identity(always=False), nullable=False),
    sa.Column('created_at', sa.DateTime(timezone=True), server_default=sa.text('now()'), nullable=False),
    sa.PrimaryKeyConstraint('id', name=op.f('pk_glossary_terms')),
    sa.UniqueConstraint('term', name=op.f('uq_glossary_terms_term'))
    )
    op.create_table('mktu_classes',
    sa.Column('class_number', sa.Integer(), nullable=False),
    sa.Column('title', sa.String(length=500), nullable=False),
    sa.Column('description', sa.Text(), nullable=True),
    sa.Column('id', sa.BigInteger(), sa.Identity(always=False), nullable=False),
    sa.CheckConstraint('class_number BETWEEN 1 AND 45', name=op.f('ck_mktu_classes_class_number_range')),
    sa.PrimaryKeyConstraint('id', name=op.f('pk_mktu_classes')),
    sa.UniqueConstraint('class_number', name=op.f('uq_mktu_classes_class_number'))
    )
    op.create_table('users',
    sa.Column('email', sa.String(length=320), nullable=False),
    sa.Column('password_hash', sa.String(length=255), nullable=False),
    sa.Column('full_name', sa.String(length=255), nullable=False),
    sa.Column('user_type', postgresql.ENUM('individual', 'organization', 'lawyer', 'admin', name='user_type', create_type=False), nullable=False),
    sa.Column('last_login_at', sa.DateTime(timezone=True), nullable=True),
    sa.Column('is_active', sa.Boolean(), server_default=sa.text('true'), nullable=False),
    sa.Column('id', sa.BigInteger(), sa.Identity(always=False), nullable=False),
    sa.Column('created_at', sa.DateTime(timezone=True), server_default=sa.text('now()'), nullable=False),
    sa.Column('updated_at', sa.DateTime(timezone=True), server_default=sa.text('now()'), nullable=False),
    sa.PrimaryKeyConstraint('id', name=op.f('pk_users')),
    sa.UniqueConstraint('email', name=op.f('uq_users_email'))
    )
    op.create_table('assessment_questions',
    sa.Column('survey_id', sa.BigInteger(), nullable=False),
    sa.Column('text', sa.Text(), nullable=False),
    sa.Column('question_type', postgresql.ENUM('single_choice', 'multiple_choice', 'text', 'boolean', name='question_type', create_type=False), nullable=False),
    sa.Column('sort_order', sa.Integer(), server_default=sa.text('0'), nullable=False),
    sa.Column('is_required', sa.Boolean(), server_default=sa.text('true'), nullable=False),
    sa.Column('id', sa.BigInteger(), sa.Identity(always=False), nullable=False),
    sa.CheckConstraint('sort_order >= 0', name=op.f('ck_assessment_questions_sort_order_nonnegative')),
    sa.ForeignKeyConstraint(['survey_id'], ['assessment_surveys.id'], name=op.f('fk_assessment_questions_survey_id_assessment_surveys'), ondelete='CASCADE'),
    sa.PrimaryKeyConstraint('id', name=op.f('pk_assessment_questions'))
    )
    op.create_index(op.f('ix_assessment_questions_survey_id'), 'assessment_questions', ['survey_id'], unique=False)
    op.create_table('content_items',
    sa.Column('category_id', sa.BigInteger(), nullable=True),
    sa.Column('type', postgresql.ENUM('article', 'guide', 'faq', 'news', name='content_type', create_type=False), nullable=False),
    sa.Column('title', sa.String(length=500), nullable=False),
    sa.Column('slug', sa.String(length=255), nullable=False),
    sa.Column('summary', sa.Text(), nullable=True),
    sa.Column('status', postgresql.ENUM('draft', 'published', 'archived', name='content_status', create_type=False), server_default=sa.text("'draft'"), nullable=False),
    sa.Column('published_at', sa.DateTime(timezone=True), nullable=True),
    sa.Column('created_by', sa.BigInteger(), nullable=True),
    sa.Column('id', sa.BigInteger(), sa.Identity(always=False), nullable=False),
    sa.Column('created_at', sa.DateTime(timezone=True), server_default=sa.text('now()'), nullable=False),
    sa.Column('updated_at', sa.DateTime(timezone=True), server_default=sa.text('now()'), nullable=False),
    sa.CheckConstraint("status <> 'published' OR published_at IS NOT NULL", name=op.f('ck_content_items_publication_date')),
    sa.ForeignKeyConstraint(['category_id'], ['content_categories.id'], name=op.f('fk_content_items_category_id_content_categories'), ondelete='RESTRICT'),
    sa.ForeignKeyConstraint(['created_by'], ['users.id'], name=op.f('fk_content_items_created_by_users'), ondelete='SET NULL'),
    sa.PrimaryKeyConstraint('id', name=op.f('pk_content_items')),
    sa.UniqueConstraint('slug', name=op.f('uq_content_items_slug'))
    )
    op.create_index(op.f('ix_content_items_category_id'), 'content_items', ['category_id'], unique=False)
    op.create_index(op.f('ix_content_items_created_by'), 'content_items', ['created_by'], unique=False)
    op.create_index('ix_content_items_status_published_at', 'content_items', ['status', 'published_at'], unique=False)
    op.create_table('fee_calculations',
    sa.Column('user_id', sa.BigInteger(), nullable=False),
    sa.Column('application_type_id', sa.BigInteger(), nullable=False),
    sa.Column('is_urgent', sa.Boolean(), server_default=sa.text('false'), nullable=False),
    sa.Column('total_amount', sa.Numeric(precision=14, scale=2), nullable=False),
    sa.Column('currency', sa.String(length=3), server_default=sa.text("'RUB'"), nullable=False),
    sa.Column('input_json', postgresql.JSONB(astext_type=sa.Text()), nullable=False),
    sa.Column('breakdown_json', postgresql.JSONB(astext_type=sa.Text()), nullable=False),
    sa.Column('id', sa.BigInteger(), sa.Identity(always=False), nullable=False),
    sa.Column('created_at', sa.DateTime(timezone=True), server_default=sa.text('now()'), nullable=False),
    sa.CheckConstraint('total_amount >= 0', name=op.f('ck_fee_calculations_amount_nonnegative')),
    sa.ForeignKeyConstraint(['application_type_id'], ['application_types.id'], name=op.f('fk_fee_calculations_application_type_id_application_types'), ondelete='RESTRICT'),
    sa.ForeignKeyConstraint(['user_id'], ['users.id'], name=op.f('fk_fee_calculations_user_id_users'), ondelete='RESTRICT'),
    sa.PrimaryKeyConstraint('id', name=op.f('pk_fee_calculations'))
    )
    op.create_index(op.f('ix_fee_calculations_application_type_id'), 'fee_calculations', ['application_type_id'], unique=False)
    op.create_index(op.f('ix_fee_calculations_user_id'), 'fee_calculations', ['user_id'], unique=False)
    op.create_table('fee_rates',
    sa.Column('application_type_id', sa.BigInteger(), nullable=False),
    sa.Column('mktu_class_id', sa.BigInteger(), nullable=True),
    sa.Column('is_urgent', sa.Boolean(), server_default=sa.text('false'), nullable=False),
    sa.Column('amount', sa.Numeric(precision=14, scale=2), nullable=False),
    sa.Column('currency', sa.String(length=3), server_default=sa.text("'RUB'"), nullable=False),
    sa.Column('valid_from', sa.Date(), nullable=False),
    sa.Column('valid_to', sa.Date(), nullable=True),
    sa.Column('legal_basis', sa.Text(), nullable=False),
    sa.Column('id', sa.BigInteger(), sa.Identity(always=False), nullable=False),
    sa.CheckConstraint('amount >= 0', name=op.f('ck_fee_rates_amount_nonnegative')),
    sa.CheckConstraint('valid_to IS NULL OR valid_to >= valid_from', name=op.f('ck_fee_rates_valid_date_range')),
    sa.ForeignKeyConstraint(['application_type_id'], ['application_types.id'], name=op.f('fk_fee_rates_application_type_id_application_types'), ondelete='RESTRICT'),
    sa.ForeignKeyConstraint(['mktu_class_id'], ['mktu_classes.id'], name=op.f('fk_fee_rates_mktu_class_id_mktu_classes'), ondelete='RESTRICT'),
    sa.PrimaryKeyConstraint('id', name=op.f('pk_fee_rates'))
    )
    op.create_index(op.f('ix_fee_rates_application_type_id'), 'fee_rates', ['application_type_id'], unique=False)
    op.create_index(op.f('ix_fee_rates_mktu_class_id'), 'fee_rates', ['mktu_class_id'], unique=False)
    op.create_index('uq_fee_rates_effective', 'fee_rates', ['application_type_id', 'mktu_class_id', 'is_urgent', 'valid_from'], unique=True, postgresql_nulls_not_distinct=True)
    op.create_table('request_history',
    sa.Column('user_id', sa.BigInteger(), nullable=False),
    sa.Column('request_type', sa.String(length=100), nullable=False),
    sa.Column('request_params', postgresql.JSONB(astext_type=sa.Text()), nullable=False),
    sa.Column('response_summary', sa.Text(), nullable=True),
    sa.Column('id', sa.BigInteger(), sa.Identity(always=False), nullable=False),
    sa.Column('created_at', sa.DateTime(timezone=True), server_default=sa.text('now()'), nullable=False),
    sa.ForeignKeyConstraint(['user_id'], ['users.id'], name=op.f('fk_request_history_user_id_users'), ondelete='RESTRICT'),
    sa.PrimaryKeyConstraint('id', name=op.f('pk_request_history'))
    )
    op.create_index(op.f('ix_request_history_user_id'), 'request_history', ['user_id'], unique=False)
    op.create_table('user_documents',
    sa.Column('user_id', sa.BigInteger(), nullable=False),
    sa.Column('template_id', sa.BigInteger(), nullable=True),
    sa.Column('document_type', postgresql.ENUM('contract', 'claim', 'application', 'other', name='document_type', create_type=False), nullable=False),
    sa.Column('title', sa.String(length=500), nullable=False),
    sa.Column('status', postgresql.ENUM('draft', 'in_progress', 'completed', 'archived', name='document_status', create_type=False), server_default=sa.text("'draft'"), nullable=False),
    sa.Column('content_json', postgresql.JSONB(astext_type=sa.Text()), nullable=False),
    sa.Column('file_path', sa.String(length=1024), nullable=True),
    sa.Column('due_date', sa.Date(), nullable=True),
    sa.Column('deadline_status', postgresql.ENUM('none', 'upcoming', 'overdue', 'completed', name='deadline_status', create_type=False), server_default=sa.text("'none'"), nullable=False),
    sa.Column('reminder_sent', sa.Boolean(), server_default=sa.text('false'), nullable=False),
    sa.Column('id', sa.BigInteger(), sa.Identity(always=False), nullable=False),
    sa.Column('created_at', sa.DateTime(timezone=True), server_default=sa.text('now()'), nullable=False),
    sa.Column('updated_at', sa.DateTime(timezone=True), server_default=sa.text('now()'), nullable=False),
    sa.ForeignKeyConstraint(['template_id'], ['document_templates.id'], name=op.f('fk_user_documents_template_id_document_templates'), ondelete='SET NULL'),
    sa.ForeignKeyConstraint(['user_id'], ['users.id'], name=op.f('fk_user_documents_user_id_users'), ondelete='RESTRICT'),
    sa.PrimaryKeyConstraint('id', name=op.f('pk_user_documents'))
    )
    op.create_index(op.f('ix_user_documents_due_date'), 'user_documents', ['due_date'], unique=False)
    op.create_index(op.f('ix_user_documents_template_id'), 'user_documents', ['template_id'], unique=False)
    op.create_index(op.f('ix_user_documents_user_id'), 'user_documents', ['user_id'], unique=False)
    op.create_table('assessment_options',
    sa.Column('question_id', sa.BigInteger(), nullable=False),
    sa.Column('text', sa.Text(), nullable=False),
    sa.Column('value', sa.String(length=255), nullable=False),
    sa.Column('sort_order', sa.Integer(), server_default=sa.text('0'), nullable=False),
    sa.Column('id', sa.BigInteger(), sa.Identity(always=False), nullable=False),
    sa.CheckConstraint('sort_order >= 0', name=op.f('ck_assessment_options_sort_order_nonnegative')),
    sa.ForeignKeyConstraint(['question_id'], ['assessment_questions.id'], name=op.f('fk_assessment_options_question_id_assessment_questions'), ondelete='CASCADE'),
    sa.PrimaryKeyConstraint('id', name=op.f('pk_assessment_options'))
    )
    op.create_index(op.f('ix_assessment_options_question_id'), 'assessment_options', ['question_id'], unique=False)
    op.create_table('assessment_results',
    sa.Column('code', sa.String(length=100), nullable=False),
    sa.Column('title', sa.String(length=500), nullable=False),
    sa.Column('description', sa.Text(), nullable=False),
    sa.Column('recommended_content_id', sa.BigInteger(), nullable=True),
    sa.Column('recommended_document_template_id', sa.BigInteger(), nullable=True),
    sa.Column('id', sa.BigInteger(), sa.Identity(always=False), nullable=False),
    sa.ForeignKeyConstraint(['recommended_content_id'], ['content_items.id'], name=op.f('fk_assessment_results_recommended_content_id_content_items'), ondelete='SET NULL'),
    sa.ForeignKeyConstraint(['recommended_document_template_id'], ['document_templates.id'], name=op.f('fk_assessment_results_recommended_document_template_id_document_templates'), ondelete='SET NULL'),
    sa.PrimaryKeyConstraint('id', name=op.f('pk_assessment_results')),
    sa.UniqueConstraint('code', name=op.f('uq_assessment_results_code'))
    )
    op.create_index(op.f('ix_assessment_results_recommended_content_id'), 'assessment_results', ['recommended_content_id'], unique=False)
    op.create_index(op.f('ix_assessment_results_recommended_document_template_id'), 'assessment_results', ['recommended_document_template_id'], unique=False)
    op.create_table('content_item_chunks',
    sa.Column('content_item_id', sa.BigInteger(), nullable=False),
    sa.Column('chunk_index', sa.Integer(), nullable=False),
    sa.Column('body', sa.Text(), nullable=False),
    sa.Column('tsv', postgresql.TSVECTOR(), sa.Computed("to_tsvector('russian'::regconfig, body)", persisted=True), nullable=False),
    sa.Column('embedding', pgvector.sqlalchemy.VECTOR(dim=1024), nullable=True),
    sa.Column('id', sa.BigInteger(), sa.Identity(always=False), nullable=False),
    sa.Column('updated_at', sa.DateTime(timezone=True), server_default=sa.text('now()'), nullable=False),
    sa.CheckConstraint("btrim(body) <> ''", name=op.f('ck_content_item_chunks_body_not_blank')),
    sa.CheckConstraint('chunk_index >= 0', name=op.f('ck_content_item_chunks_chunk_index_nonnegative')),
    sa.ForeignKeyConstraint(['content_item_id'], ['content_items.id'], name=op.f('fk_content_item_chunks_content_item_id_content_items'), ondelete='CASCADE'),
    sa.PrimaryKeyConstraint('id', name=op.f('pk_content_item_chunks')),
    sa.UniqueConstraint('content_item_id', 'chunk_index', name=op.f('uq_content_item_chunks_content_item_id'))
    )
    op.create_index(op.f('ix_content_item_chunks_content_item_id'), 'content_item_chunks', ['content_item_id'], unique=False)
    op.create_index('ix_content_item_chunks_embedding', 'content_item_chunks', ['embedding'], unique=False, postgresql_using='hnsw', postgresql_ops={'embedding': 'vector_cosine_ops'})
    op.create_index('ix_content_item_chunks_tsv', 'content_item_chunks', ['tsv'], unique=False, postgresql_using='gin')
    op.create_table('content_item_tags',
    sa.Column('content_item_id', sa.BigInteger(), nullable=False),
    sa.Column('tag_id', sa.BigInteger(), nullable=False),
    sa.ForeignKeyConstraint(['content_item_id'], ['content_items.id'], name=op.f('fk_content_item_tags_content_item_id_content_items'), ondelete='CASCADE'),
    sa.ForeignKeyConstraint(['tag_id'], ['content_tags.id'], name=op.f('fk_content_item_tags_tag_id_content_tags'), ondelete='CASCADE'),
    sa.PrimaryKeyConstraint('content_item_id', 'tag_id', name=op.f('pk_content_item_tags'))
    )
    op.create_index(op.f('ix_content_item_tags_tag_id'), 'content_item_tags', ['tag_id'], unique=False)
    op.create_table('document_status_history',
    sa.Column('document_id', sa.BigInteger(), nullable=False),
    sa.Column('old_status', postgresql.ENUM('draft', 'in_progress', 'completed', 'archived', name='document_status', create_type=False), nullable=True),
    sa.Column('new_status', postgresql.ENUM('draft', 'in_progress', 'completed', 'archived', name='document_status', create_type=False), nullable=False),
    sa.Column('comment', sa.Text(), nullable=True),
    sa.Column('changed_by', sa.BigInteger(), nullable=True),
    sa.Column('changed_at', sa.DateTime(timezone=True), server_default=sa.text('now()'), nullable=False),
    sa.Column('id', sa.BigInteger(), sa.Identity(always=False), nullable=False),
    sa.ForeignKeyConstraint(['changed_by'], ['users.id'], name=op.f('fk_document_status_history_changed_by_users'), ondelete='SET NULL'),
    sa.ForeignKeyConstraint(['document_id'], ['user_documents.id'], name=op.f('fk_document_status_history_document_id_user_documents'), ondelete='RESTRICT'),
    sa.PrimaryKeyConstraint('id', name=op.f('pk_document_status_history'))
    )
    op.create_index(op.f('ix_document_status_history_changed_by'), 'document_status_history', ['changed_by'], unique=False)
    op.create_index(op.f('ix_document_status_history_document_id'), 'document_status_history', ['document_id'], unique=False)
    op.create_table('fee_calculation_classes',
    sa.Column('calculation_id', sa.BigInteger(), nullable=False),
    sa.Column('mktu_class_id', sa.BigInteger(), nullable=False),
    sa.ForeignKeyConstraint(['calculation_id'], ['fee_calculations.id'], name=op.f('fk_fee_calculation_classes_calculation_id_fee_calculations'), ondelete='CASCADE'),
    sa.ForeignKeyConstraint(['mktu_class_id'], ['mktu_classes.id'], name=op.f('fk_fee_calculation_classes_mktu_class_id_mktu_classes'), ondelete='RESTRICT'),
    sa.PrimaryKeyConstraint('calculation_id', 'mktu_class_id', name=op.f('pk_fee_calculation_classes'))
    )
    op.create_index(op.f('ix_fee_calculation_classes_mktu_class_id'), 'fee_calculation_classes', ['mktu_class_id'], unique=False)
    op.create_table('glossary_term_content',
    sa.Column('term_id', sa.BigInteger(), nullable=False),
    sa.Column('content_item_id', sa.BigInteger(), nullable=False),
    sa.ForeignKeyConstraint(['content_item_id'], ['content_items.id'], name=op.f('fk_glossary_term_content_content_item_id_content_items'), ondelete='CASCADE'),
    sa.ForeignKeyConstraint(['term_id'], ['glossary_terms.id'], name=op.f('fk_glossary_term_content_term_id_glossary_terms'), ondelete='CASCADE'),
    sa.PrimaryKeyConstraint('term_id', 'content_item_id', name=op.f('pk_glossary_term_content'))
    )
    op.create_index(op.f('ix_glossary_term_content_content_item_id'), 'glossary_term_content', ['content_item_id'], unique=False)
    op.create_table('qa_pairs',
    sa.Column('question', sa.Text(), nullable=False),
    sa.Column('answer', sa.Text(), nullable=False),
    sa.Column('category_id', sa.BigInteger(), nullable=True),
    sa.Column('content_item_id', sa.BigInteger(), nullable=True),
    sa.Column('sort_order', sa.Integer(), server_default=sa.text('0'), nullable=False),
    sa.Column('id', sa.BigInteger(), sa.Identity(always=False), nullable=False),
    sa.CheckConstraint('sort_order >= 0', name=op.f('ck_qa_pairs_sort_order_nonnegative')),
    sa.ForeignKeyConstraint(['category_id'], ['content_categories.id'], name=op.f('fk_qa_pairs_category_id_content_categories'), ondelete='SET NULL'),
    sa.ForeignKeyConstraint(['content_item_id'], ['content_items.id'], name=op.f('fk_qa_pairs_content_item_id_content_items'), ondelete='SET NULL'),
    sa.PrimaryKeyConstraint('id', name=op.f('pk_qa_pairs'))
    )
    op.create_index(op.f('ix_qa_pairs_category_id'), 'qa_pairs', ['category_id'], unique=False)
    op.create_index(op.f('ix_qa_pairs_content_item_id'), 'qa_pairs', ['content_item_id'], unique=False)
    op.create_table('assessment_result_rules',
    sa.Column('survey_id', sa.BigInteger(), nullable=False),
    sa.Column('result_id', sa.BigInteger(), nullable=False),
    sa.Column('condition_json', postgresql.JSONB(astext_type=sa.Text()), nullable=False),
    sa.Column('priority', sa.Integer(), server_default=sa.text('0'), nullable=False),
    sa.Column('id', sa.BigInteger(), sa.Identity(always=False), nullable=False),
    sa.ForeignKeyConstraint(['result_id'], ['assessment_results.id'], name=op.f('fk_assessment_result_rules_result_id_assessment_results'), ondelete='RESTRICT'),
    sa.ForeignKeyConstraint(['survey_id'], ['assessment_surveys.id'], name=op.f('fk_assessment_result_rules_survey_id_assessment_surveys'), ondelete='CASCADE'),
    sa.PrimaryKeyConstraint('id', name=op.f('pk_assessment_result_rules'))
    )
    op.create_index(op.f('ix_assessment_result_rules_result_id'), 'assessment_result_rules', ['result_id'], unique=False)
    op.create_index(op.f('ix_assessment_result_rules_survey_id'), 'assessment_result_rules', ['survey_id'], unique=False)
    op.create_table('user_assessments',
    sa.Column('user_id', sa.BigInteger(), nullable=False),
    sa.Column('survey_id', sa.BigInteger(), nullable=False),
    sa.Column('result_id', sa.BigInteger(), nullable=True),
    sa.Column('answers_json', postgresql.JSONB(astext_type=sa.Text()), nullable=False),
    sa.Column('id', sa.BigInteger(), sa.Identity(always=False), nullable=False),
    sa.Column('created_at', sa.DateTime(timezone=True), server_default=sa.text('now()'), nullable=False),
    sa.ForeignKeyConstraint(['result_id'], ['assessment_results.id'], name=op.f('fk_user_assessments_result_id_assessment_results'), ondelete='RESTRICT'),
    sa.ForeignKeyConstraint(['survey_id'], ['assessment_surveys.id'], name=op.f('fk_user_assessments_survey_id_assessment_surveys'), ondelete='RESTRICT'),
    sa.ForeignKeyConstraint(['user_id'], ['users.id'], name=op.f('fk_user_assessments_user_id_users'), ondelete='RESTRICT'),
    sa.PrimaryKeyConstraint('id', name=op.f('pk_user_assessments'))
    )
    op.create_index(op.f('ix_user_assessments_result_id'), 'user_assessments', ['result_id'], unique=False)
    op.create_index(op.f('ix_user_assessments_survey_id'), 'user_assessments', ['survey_id'], unique=False)
    op.create_index(op.f('ix_user_assessments_user_id'), 'user_assessments', ['user_id'], unique=False)

    op.execute("""
        CREATE FUNCTION melawdy_touch_updated_at() RETURNS trigger
        LANGUAGE plpgsql AS $$
        BEGIN
            NEW.updated_at = clock_timestamp();
            RETURN NEW;
        END;
        $$
    """)
    for table in ("users", "content_items", "document_templates", "user_documents"):
        op.execute(
            f"CREATE TRIGGER tr_{table}_updated_at BEFORE UPDATE ON {table} "
            "FOR EACH ROW EXECUTE FUNCTION melawdy_touch_updated_at()"
        )
    op.execute("""
        CREATE FUNCTION melawdy_touch_chunk() RETURNS trigger
        LANGUAGE plpgsql AS $$
        BEGIN
            IF NEW.body IS DISTINCT FROM OLD.body THEN
                NEW.embedding = NULL;
            END IF;
            NEW.updated_at = clock_timestamp();
            RETURN NEW;
        END;
        $$
    """)
    op.execute("""
        CREATE TRIGGER tr_content_item_chunks_updated_at
        BEFORE UPDATE ON content_item_chunks
        FOR EACH ROW EXECUTE FUNCTION melawdy_touch_chunk()
    """)


def downgrade() -> None:
    op.drop_table('user_assessments')
    op.drop_table('assessment_result_rules')
    op.drop_table('qa_pairs')
    op.drop_table('glossary_term_content')
    op.drop_table('fee_calculation_classes')
    op.drop_table('document_status_history')
    op.drop_table('content_item_tags')
    op.drop_table('content_item_chunks')
    op.drop_table('assessment_results')
    op.drop_table('assessment_options')
    op.drop_table('user_documents')
    op.drop_table('request_history')
    op.drop_table('fee_rates')
    op.drop_table('fee_calculations')
    op.drop_table('content_items')
    op.drop_table('assessment_questions')
    op.drop_table('users')
    op.drop_table('mktu_classes')
    op.drop_table('glossary_terms')
    op.drop_table('document_templates')
    op.drop_table('content_tags')
    op.drop_table('content_categories')
    op.drop_table('assessment_surveys')
    op.drop_table('application_types')

    op.execute("DROP FUNCTION melawdy_touch_chunk()")
    op.execute("DROP FUNCTION melawdy_touch_updated_at()")
    op.execute("DROP TYPE content_status")
    op.execute("DROP TYPE content_type")
    op.execute("DROP TYPE deadline_status")
    op.execute("DROP TYPE document_status")
    op.execute("DROP TYPE document_type")
    op.execute("DROP TYPE question_type")
    op.execute("DROP TYPE user_type")
