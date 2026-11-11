from typing import Literal

from pydantic import BaseModel, Field, field_validator, model_validator


class SupplierFacts(BaseModel):
    """Результат extractor-агента: структурированные факты из текста поставщика."""

    product_name: str = Field(description="Название товара из текста поставщика")
    characteristics: dict[str, str] = Field(
        default_factory=dict, description="Характеристики: ключ-значение"
    )
    missing_fields: list[str] = Field(
        default_factory=list,
        description="Что не найдено в тексте (например: гарантия, цвет)",
    )

class SeoBlock(BaseModel):
    meta_title: str = Field(
        max_length=60,
        description="SEO-заголовок страницы",
    )
    meta_description: str = Field(
        max_length=160,
        description="SEO-описание страницы",
    )

class SourceReference(BaseModel):
    url: str = Field(
        min_length=1,
        description="Адрес источника информации",
    )
    description: str | None = Field(
        default=None,
        description="Описание источника",
    )

class CardDraft(BaseModel):
    """Результат generator-агента: черновик карточки товара."""

    title: str = Field(
        max_length=60,
        description="Заголовок карточки, до 60 символов",
    )
    description: str = Field(description="Описание на 3-4 предложения")
    characteristics: dict[str, str] = Field(default_factory=dict)
    benefits: list[str] = Field(default_factory=list)
    missing_fields: list[str] = Field(
        default_factory=list,
        description="Характеристики, отсутствующие в данных поставщика",
    )
    confidence: float = Field(
        ge=0.0,
        le=1.0,
        description="Уверенность модели в достоверности карточки",
    )
    seo: SeoBlock | None = Field(
        default=None,
        description="SEO-метаданные карточки товара",
    )
    sources: list[SourceReference] = Field(
        default_factory=list,
        description="Источники информации о товаре",
    )
    @field_validator("characteristics")
    @classmethod
    def remove_empty_characteristics(
        cls, value: dict[str, str]
    ) -> dict[str, str]:
        return {
            key: item.strip()
            for key, item in value.items()
            if item.strip()
        }
    @model_validator(mode="after")
    def check_missing_fields(self):
        overlap = (
            set(self.characteristics)
            & set(self.missing_fields)
        )

        if overlap:
            raise ValueError(
                f"Поля одновременно присутствуют в "
                f"характеристиках и списке недостающих: "
                f"{sorted(overlap)}"
            )

        return self

class CritiqueReport(BaseModel):
    """Результат critic-агента: вердикт и список проблем."""

    verdict: Literal["approve", "regenerate"] = Field(
        description="approve — карточка годится; regenerate — переделать"
    )
    issues: list[str] = Field(
        default_factory=list,
        description="Список проблем: заголовок длиннее 60 символов, "
        "выдуманные характеристики, пустые поля и т.п.",
    )


class JobIn(BaseModel):
    supplier_text: str


class JobOut(BaseModel):
    id: str
    status: str
    attempts: int
    result: CardDraft | None = None
    error: str | None = None
