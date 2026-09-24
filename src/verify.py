import csv
import json
import re
from pathlib import Path

from config import LLM_EFFORT, LLM_MAX_TOKENS, LLM_MODEL, get_llm_client
from corpus import load_paragraphs, normalise
from llm import _log_run

GOLD_PATH = Path(__file__).parent.parent / "corpus" / "corpus_gold_standard.csv"
LOCATOR = re.compile(r"ch\s*(\d+)\s*p\s*(\d+)", re.I)

# never pass the gold standard's own description of a candidate — several rows
# telegraph the answer. type, entities and passages only, as the graph would.
VERIFY_PROMPT = """A consistency checker has flagged the passages below as a \
possible {type} contradiction involving: {entities}.

Decide whether they actually contradict. Two statements contradict only if they \
cannot both be true of the same story world. Statements about different people, \
different times, different places or different groups do not contradict, and \
neither does a change that can legitimately occur.

Return JSON only:

{{"verdict": "CONTRADICTION|CONSISTENT", "confidence": "high|medium|low", \
"reason": "one sentence"}}

PASSAGES:

{passages}
"""


def load_candidates():
    """Live gold standard rows as verification candidates.

    Ground truth comes from Origin: naturally occurring rows are real
    contradictions, legitimate rows are not.
    """
    paragraphs = {(p.chapter, p.index): normalise(p.text) for p in load_paragraphs()}
    candidates = []

    with open(GOLD_PATH, encoding="utf-8-sig", newline="") as f:
        for row in csv.DictReader(f):
            if (row.get("Status") or "").strip().upper() == "RETIRED":
                continue

            locators = []
            for chapter, index in LOCATOR.findall(row["Approx. sentence / locator"]):
                key = (int(chapter), int(index))
                if key not in locators:
                    locators.append(key)

            candidates.append(
                {
                    "id": row["ID"],
                    "type": row["Type"],
                    "entities": row["Entities involved"],
                    "truth": "CONTRADICTION"
                    if row["Origin"].strip().lower().startswith("natural")
                    else "CONSISTENT",
                    "passages": "\n\n".join(
                        f"[ch{c}:p{i}] {paragraphs[(c, i)]}" for c, i in locators
                    ),
                }
            )

    return candidates


def verify_candidate(candidate, client=None):
    client = client or get_llm_client()
    prompt = VERIFY_PROMPT.format(
        type=candidate["type"],
        entities=candidate["entities"],
        passages=candidate["passages"],
    )

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
    log_path = _log_run(f"verify_{candidate['id']}", prompt, message)

    try:
        result = json.loads(response_text)
    except json.JSONDecodeError:
        result = {"verdict": "UNPARSEABLE", "confidence": None, "reason": ""}

    return result, log_path


def main():
    client = get_llm_client()
    candidates = load_candidates()
    counts = {"tp": 0, "fp": 0, "tn": 0, "fn": 0, "bad": 0}

    for candidate in candidates:
        result, _ = verify_candidate(candidate, client)
        verdict = result.get("verdict")
        truth = candidate["truth"]

        if verdict not in ("CONTRADICTION", "CONSISTENT"):
            key = "bad"
        elif truth == "CONTRADICTION":
            key = "tp" if verdict == "CONTRADICTION" else "fn"
        else:
            key = "fp" if verdict == "CONTRADICTION" else "tn"
        counts[key] += 1

        mark = "ok " if key in ("tp", "tn") else "MISS"
        print(f"{mark} {candidate['id']:6} truth={truth:14} said={verdict:14} "
              f"[{result.get('confidence')}] {result.get('reason', '')[:80]}")

    print(
        f"\ntrue positives {counts['tp']}  false negatives {counts['fn']}  "
        f"true negatives {counts['tn']}  false positives {counts['fp']}  "
        f"unparseable {counts['bad']}"
    )


if __name__ == "__main__":
    main()