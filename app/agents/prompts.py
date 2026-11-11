"""Промпт как код: три агента кард-пайплайна — extractor, generator, critic.

Прямые наследники агентов из Занятия 1 (demo.py) — та же модель,
тот же паттерн дублирования схемы текстом в промпте (LM Studio не
поддерживает strict JSON mode).
"""
import json

from agents import Agent, AgentOutputSchema, ModelSettings

from app.core.config import settings
from app.schemas import CardDraft, CritiqueReport, SupplierFacts

_MODEL = settings.llm_model

# Reasoning-модели (gemma-4 и т.п.) тратят токены на «размышления» до ответа:
# без запаса max_tokens бюджет кончается раньше content, и LM Studio
# обрывает stream по таймауту. 4096 хватает на размышления + JSON-ответ.
_MODEL_SETTINGS = ModelSettings(max_tokens=4096, temperature=0)

extractor_agent = Agent(
    name="Extractor",
    instructions=(
        "Ты — извлекатель фактов. Из текста поставщика выдели структурированные факты.\n"
        "Верни СТРОГО JSON с этими полями и никаких других:\n"
        "- product_name (string): название товара\n"
        "- characteristics (object): пары ключ-значение, ТОЛЬКО из текста\n"
        "- missing_fields (array of string): что важно для карточки, но в тексте нет "
        "(например: гарантия, цвет, страна-производитель)\n"
        "Не выдумывай. Нет данных — поле в missing_fields. "
        "Перед ответом проверь: если характеристика уже есть "
        "в characteristics, не включай её в missing_fields. "
        "Сравнивай названия без учёта регистра букв. "
        "Никакого markdown, только валидный JSON."
    ),
    model=_MODEL,
    model_settings=_MODEL_SETTINGS,
    output_type=AgentOutputSchema(SupplierFacts, strict_json_schema=False),
)

generator_agent = Agent(
    name="Generator",
    instructions=(
        "Ты — копирайтер маркетплейса. Из фактов о товаре сделай черновик карточки.\n"
        "Верни СТРОГО JSON с этими полями и никаких других:\n"
        "- title (string): заголовок до 60 символов\n"
        "- description (string): описание на 3-4 предложения, продающее, без воды\n"
        "- characteristics (object): характеристики ключ-значение\n"
        "- benefits (array of string): 3-5 преимуществ\n"
        "- missing_fields (array of string): характеристики, которых нет в исходных фактах\n"
        "- confidence (number от 0 до 1): уверенность в достоверности карточки; "
        "при недостатке данных снижай уверенность\n"
        "- seo (object или null): meta_title до 60 символов, "
        "meta_description до 160 символов\n"
        "- sources (array of object): источники с полями url и description; "
        "не придумывай ссылки, если источники не предоставлены — верни []\n"        
        "Используй только предоставленные факты. Если есть замечания критика "
        "(feedback) — учти их. Никакого markdown, только валидный JSON."
    ),
    model=_MODEL,
    model_settings=_MODEL_SETTINGS,
    output_type=None,
)

critic_agent = Agent(
    name="Critic",
    instructions=(
        "Ты — строгий редактор карточек маркетплейса. Проверь черновик по правилам:\n"
        "1. title не длиннее 60 символов\n"
        "2. Нет характеристик, которых нет в фактах (выдуманные)\n"
        "3. description и benefits не пустые\n"
        "4. Нет воды («высокое качество», «лучшая цена») без конкретики\n"
        "Верни СТРОГО JSON:\n"
        '- verdict (string): "approve" если всё ок, иначе "regenerate"\n'
        "- issues (array of string): список проблем; при approve — пустой\n"
        "Никакого markdown, только валидный JSON."
    ),
    model=_MODEL,
    model_settings=_MODEL_SETTINGS,
    output_type=AgentOutputSchema(CritiqueReport, strict_json_schema=False),
)

def extractor_prompt(supplier_text: str) -> str:
    """Подготовить текст поставщика для извлечения фактов."""
    return supplier_text

def generator_prompt(
    facts: SupplierFacts,
    feedback: list[str] | None = None,
) -> str:
    """Сформировать запрос для генерации карточки товара."""

    prompt = (
            "Факты о товаре:\n"
            + facts.model_dump_json(indent=2)
            + "\n\nФормат ответа — JSON по следующей схеме:\n"
            + json.dumps(
        CardDraft.model_json_schema(),
        ensure_ascii=False,
        indent=2,
    )
    )

    if feedback:
        prompt += "\n\nЗамечания критика, учти:\n"
        prompt += "\n".join(f"- {issue}" for issue in feedback)

    return prompt

def healing_prompt(
    original_prompt: str,
    invalid_response: str,
    validation_error: str,
) -> str:
    """Сформировать запрос на исправление невалидного ответа LLM."""
    return (
        original_prompt
        + "\n\nПредыдущий ответ модели:\n"
        + invalid_response
        + "\n\nОшибка проверки:\n"
        + validation_error
        + "\n\nИсправь только ошибки, указанные выше. "
        "Сохрани все остальные корректные данные. "
        "Верни полный исправленный JSON без пояснений."
    )

def field_repair_prompt(
    draft: dict,
    field_name: str,
    validation_error: str,
) -> str:
    """Запросить исправление только одного поля карточки."""
    return (
        "Перед тобой текущий черновик карточки:\n"
        + json.dumps(draft, ensure_ascii=False, indent=2)
        + "\n\nИсправь только поле: "
        + field_name
        + "\nОшибка проверки:\n"
        + validation_error
        + "\n\nНе изменяй другие поля. "
        "Верни JSON-объект только с исправленным полем, "
        "без markdown и пояснений."
    )

def critic_prompt(
    facts: SupplierFacts,
    draft: CardDraft,
) -> str:
    """Сформировать запрос для проверки карточки товара."""
    return (
        "Факты о товаре:\n"
        + facts.model_dump_json(indent=2)
        + "\n\nЧерновик карточки для проверки:\n"
        + draft.model_dump_json(indent=2)
    )
