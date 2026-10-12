from backend.schemas import AnalyzeResponse


def analyze(_question: str) -> AnalyzeResponse:
    """Stable API contract until retrieval and ranking are implemented."""
    return AnalyzeResponse(
        status="not_implemented",
        model_ready=False,
        message="Анализ вопроса пока не настроен.",
    )
