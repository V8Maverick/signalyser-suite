"""Large-input handling: cloud single-shots; local maps-reduces to fit context.

Cloud Claude has a huge context window, so it analyzes big inputs (10-Ks, long
pages) in one pass. Local Qwen can't, so for oversized inputs we summarize the
document in context-sized chunks and then synthesize the partial extracts.
"""
import os

from .processing import analyze

# Default per-chunk character budget for local models (~ conservative for 8K ctx).
DEFAULT_CHAR_BUDGET = 12000

# Total corpus chars to hand a local model in ONE shot (corpus-wide tools like the
# CTA tracker / quadrant). Persona files alone can be ~15K chars each, so a 5-company
# corpus blows past an 8K context and the model returns nothing. Trim to fit.
LOCAL_CORPUS_BUDGET = 12000


def fit_corpus_for_local(combined: dict[str, str], processor: str,
                         char_budget: int | None = None) -> dict[str, str]:
    """Trim a {company: text} corpus so a local model can read it in one pass.

    Cloud is returned untouched (huge context). For local, if the corpus exceeds
    the budget, each company's text is truncated to an even share (page copy comes
    first in each block, so the CTA-relevant content is what's kept). Prints a notice.
    """
    if processor == "cloud":
        return combined
    budget = char_budget if char_budget is not None else \
        int(os.getenv("LOCAL_CORPUS_BUDGET", str(LOCAL_CORPUS_BUDGET)))
    total = sum(len(v) for v in combined.values())
    if total <= budget or not combined:
        return combined
    per = max(1200, budget // len(combined))
    trimmed: dict[str, str] = {}
    for name, text in combined.items():
        if len(text) > per:
            trimmed[name] = text[:per].rstrip() + "\n\n…[trimmed to fit the local model]"
        else:
            trimmed[name] = text
    print(
        f"\n[local] Corpus is {total:,} chars — trimming each of the {len(combined)} "
        f"companies to ~{per:,} chars so the local model can read it. The full corpus "
        "is used on cloud (-p cloud); or raise OLLAMA_NUM_CTX / LOCAL_CORPUS_BUDGET.\n"
    )
    return trimmed

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
