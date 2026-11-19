from dataclasses import dataclass


@dataclass
class ContextResult:
    text: str
    fragment_ids: list[str]
    size: int

def format_fragment(fragment: dict) -> str:
    lines = [
        f"[fragment_id: {fragment['id']}]",
        f"document_id: {fragment['document_id']}",
        f"ord: {fragment['ord']}",
    ]

    for field in ("page", "section", "article", "brand"):
        value = fragment.get(field)
        if value is not None and value != "":
            lines.append(f"{field}: {value}")

    lines.append("")
    lines.append(fragment["text"].strip())

    return "\n".join(lines)

def build_context(
    fragments: list[dict],
    max_chars: int = 6000,
) -> ContextResult:
    blocks: list[str] = []
    fragment_ids: list[str] = []

    seen_ids: set[str] = set()
    seen_texts: set[str] = set()

    current_size = 0
    separator = "\n\n"

    for fragment in fragments:
        fragment_id = fragment["id"]
        normalized_text = " ".join(fragment["text"].split())

        if not normalized_text:
            continue

        if fragment_id in seen_ids:
            continue

        if normalized_text in seen_texts:
            continue

        block = format_fragment(fragment)

        additional_size = len(block)
        if blocks:
            additional_size += len(separator)

        if current_size + additional_size > max_chars:
            continue

        blocks.append(block)
        fragment_ids.append(fragment_id)

        seen_ids.add(fragment_id)
        seen_texts.add(normalized_text)

        current_size += additional_size

    return ContextResult(
        text=separator.join(blocks),
        fragment_ids=fragment_ids,
        size=current_size,
    )
