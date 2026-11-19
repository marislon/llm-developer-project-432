from app.agents.prompts import (
    rag_critic_prompt,
    rag_generator_prompt,
)
from app.schemas import CardDraft


def test_rag_generator_prompt():
    context = (
        "[fragment_id: frag-001]\n"
        "Мощность: 2200 Вт."
    )

    product_hint = "Электрический чайник KTL-1700"

    feedback = ["Указан несуществующий fragment_id"]

    prompt = rag_generator_prompt(
        context=context,
        product_hint=product_hint,
        feedback=feedback,
    )

    assert context in prompt
    assert product_hint in prompt
    assert feedback[0] in prompt
    assert '"fragment_id"' in prompt
    assert '"sources"' in prompt
    assert '"missing_fields"' in prompt
    assert '"confidence"' in prompt

def test_rag_critic_prompt():
    context = (
        "[fragment_id: frag-001]\n"
        "Мощность: 2200 Вт."
    )

    product_hint = "Электрический чайник KTL-1700"

    draft = CardDraft(
        title="Электрический чайник KTL-1700",
        description="Чайник мощностью 2200 Вт.",
        characteristics={"Мощность": "2200 Вт"},
        benefits=["Мощность 2200 Вт"],
        missing_fields=["Гарантия"],
        confidence=0.8,
        sources=[
            {
                "fragment_id": "frag-001",
                "description": "Мощность: 2200 Вт.",
            },
        ],
    )

    prompt = rag_critic_prompt(
        context=context,
        draft=draft,
        product_hint=product_hint,
    )

    assert context in prompt
    assert product_hint in prompt
    assert draft.model_dump_json(indent=2) in prompt
    assert '"verdict"' in prompt
    assert '"issues"' in prompt
    assert '"sources"' in prompt
    assert '"fragment_id"' in prompt
