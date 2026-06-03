"""Large-input handling: cloud single-shots; local maps-reduces to fit context.

Cloud Claude has a huge context window, so it analyzes big inputs (10-Ks, long
pages) in one pass. Local Qwen can't, so for oversized inputs we summarize the
document in context-sized chunks and then synthesize the partial extracts.
"""
from .processing import analyze

# Default per-chunk character budget for local models (~ conservative for 8K ctx).
DEFAULT_CHAR_BUDGET = 12000

_MAP_SYSTEM = (
    "You are an analyst extracting the key facts from one chunk of a larger "
    "document. Be concise and faithful — capture concrete claims, numbers, names, "
    "and language verbatim where useful. Do not add commentary or conclusions; a "
    "later step will synthesize across all chunks."
)


def analyze_large(system_prompt: str, header: str, body: str, *,
                  processor: str, model_key: str | None,
                  char_budget: int = DEFAULT_CHAR_BUDGET,
                  max_tokens: int = 8192) -> str:
    """Analyze a large body of text under the given system prompt.

    Cloud (or a body that already fits) → single pass. Local + oversized → a
    map-reduce: per-chunk extraction, then a final synthesis under `system_prompt`.
    """
    if processor == "cloud" or len(body) <= char_budget:
        return analyze(system_prompt, f"{header}\n\n{body}",
                       processor=processor, model_key=model_key, max_tokens=max_tokens)

    chunks = [body[i:i + char_budget] for i in range(0, len(body), char_budget)]
    print(
        f"\n[chunking] Local model: input {len(body)} chars exceeds the "
        f"{char_budget}-char budget — map-reducing across {len(chunks)} chunks. "
        "This is slower and lossier than cloud; use -p cloud for a single pass.\n"
    )
    partials: list[str] = []
    for i, chunk in enumerate(chunks, 1):
        print(f"\n[chunk {i}/{len(chunks)}]")
        partials.append(analyze(
            _MAP_SYSTEM,
            f"{header}\n\n(Chunk {i} of {len(chunks)})\n\n{chunk}",
            processor=processor, model_key=model_key,
        ))
    combined = "\n\n---\n\n".join(partials)
    print(f"\n[synthesis] Combining {len(chunks)} extracts into the final report.\n")
    return analyze(
        system_prompt,
        f"{header}\n\nSynthesize the final report from these per-chunk extracts:\n\n{combined}",
        processor=processor, model_key=model_key, max_tokens=max_tokens,
    )
