import json
from datetime import datetime, timezone
from pathlib import Path

from config import LLM_MODEL, get_llm_client, LLM_EFFORT, LLM_MAX_TOKENS
from corpus import CORPUS_PATH, load_paragraphs, normalise

RUNS_DIR = Path(__file__).parent.parent / "llm_runs"

# prompt is an instrument — versioned like code. Says nothing about what counts
# as legitimate change; naming clothes or hairstyles would hand it the precision test.
DETECTION_PROMPT = """You are checking a fiction manuscript for internal \
contradictions.

Below are two chapters, with each paragraph tagged [chN:pM].

Report every place where two statements in the text cannot both be true of the \
same story world. Judge only against the text itself. Do not report anything \
that is merely unusual, unexplained, or not yet resolved.

Return JSON only, no prose, in exactly this shape:

{"findings": [
  {
    "type": "timeline|attribute|number|location|relationship|alias|other",
    "scope": "within-sentence|within-chapter|cross-chapter",
    "summary": "one sentence stating the contradiction",
    "evidence": ["exact quote from the text", "exact quote from the text"],
    "locations": ["ch1:p21", "ch2:p7"],
    "confidence": "high|medium|low"
  }
]}

Quotes in "evidence" must be copied verbatim from the text so they can be \
located. If you find nothing, return {"findings": []}.

MANUSCRIPT:

"""


def format_corpus():
    """Tagged paragraphs from the frozen corpus.

    Same loader as the pipeline, so the LLM and the graph read identical text.
    Tags match the gold standard's locator scheme.
    """
    return "\n\n".join(
        f"[ch{p.chapter}:p{p.index}] {normalise(p.text)}" for p in load_paragraphs()
    )


def _log_run(kind, prompt, message):
    """Write the raw call to disk. This is the evidence, not the parsed table."""
    RUNS_DIR.mkdir(exist_ok=True)
    stamp = datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%SZ")
    path = RUNS_DIR / f"{kind}_{CORPUS_PATH.stem}_{stamp}.json"
    path.write_text(
        json.dumps(
            {
                "kind": kind,
                "model": LLM_MODEL,
                "corpus": CORPUS_PATH.name,
                "timestamp": stamp,
                "input_tokens": message.usage.input_tokens,
                "output_tokens": message.usage.output_tokens,
                "stop_reason": message.stop_reason,
                "prompt": prompt,
                "content": [block.model_dump() for block in message.content],
            },
            indent=2,
        ),
        encoding="utf-8",
    )
    return path


def detect_inconsistencies(client=None):
    """Find contradictions in the frozen corpus, cold.

    One call for both chapters so cross-chapter cases are reachable. findings is
    empty if the JSON won't parse; the log always holds the raw response.
    """
    client = client or get_llm_client()
    prompt = DETECTION_PROMPT + format_corpus()

    # stream, not create: the SDK refuses a blocking call whose budget could
    # run past 10 minutes.
    with client.messages.stream(
        model=LLM_MODEL,
        max_tokens=LLM_MAX_TOKENS,
        thinking={"type": "adaptive"},
        output_config={"effort": LLM_EFFORT},
        messages=[{"role": "user", "content": prompt}],
    ) as stream:
        message = stream.get_final_message()
    response_text = "".join(
        block.text for block in message.content if getattr(block, "type", None) == "text"
    )
    log_path = _log_run("detect", prompt, message)
    try:
        findings = json.loads(response_text)["findings"]
    except (json.JSONDecodeError, KeyError, IndexError):
        findings = []

    return findings, log_path


if __name__ == "__main__":
    findings, log_path = detect_inconsistencies()
    print(f"{len(findings)} findings, raw response in {log_path.name}")
    for f in findings:
        print(f"\n  [{f.get('confidence')}] {f.get('type')} / {f.get('scope')}")
        print(f"  {f.get('summary')}")
        for loc in f.get("locations", []):
            print(f"    {loc}")