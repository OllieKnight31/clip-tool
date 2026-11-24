"""Optional: automatic clip selection through the Anthropic API.

Normal use does NOT need this file or an API key: inside Claude Code, Claude
reads the transcript and writes the decisions file itself. This module exists
for unattended runs (see pick_clips.py).

Input: full transcript with word-level timestamps + your brand voice notes.
Output: a list of clips, each with KEEP segments (non-contiguous time ranges,
filler removed), a headline and a topic slug.
"""
import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
import config

EXAMPLE_VOICE = Path(__file__).resolve().parent / "brand_voice.example.md"


def load_brand_voice() -> str:
    """Your own notes if you have written them, otherwise the neutral example."""
    for candidate in (config.BRAND_VOICE_FILE, EXAMPLE_VOICE):
        if candidate.exists():
            return candidate.read_text(encoding="utf-8")
    return "No brand voice notes supplied. Pick the clearest, most self-contained moments."


def build_system_prompt() -> str:
    return f"""You are the video clip editor for {config.CREATOR_NAME}. You take a long-form
transcript and return short-form vertical clips that hold attention.

Your output is the EDIT DECISION LIST: exact word-aligned timestamps to KEEP from the source,
in the order they should play. You can splice non-contiguous segments together to remove filler,
restarts, tangents and dead air, while preserving meaning and voice.

# Brand voice and selection criteria (use this to score what is worth clipping)
{load_brand_voice()}

# Hard rules
- Each clip must be 30-120 seconds total (after stitching).
- Cut filler: "um", "uh", "like" (filler use only, keep when meaningful), "you know", "right?"
  used as rhetorical filler, repeated stutters ("I-I-I think" becomes "I think"), restart phrases
  ("what I'm, what I'm saying is" becomes "what I'm saying is").
- Cut dead air longer than 600ms unless it is a deliberate dramatic pause that LANDS the line.
- Splice non-contiguous segments only when the result reads as one coherent thought.
  Do NOT splice across topic changes. The viewer should not feel the cut.
- Cut at WORD BOUNDARIES using the word timestamps provided. Never invent a timestamp.
- The first KEEP segment must start with a strong opening line, not mid-sentence.
- The last KEEP segment must end with a landed thought, not mid-clause.

# Output format (JSON only, no prose, no code fences)
{{
  "clips": [
    {{
      "headline": "lowercase 3-7 word title for top of clip",
      "rationale": "one sentence why this clip is worth posting",
      "topic_slug": "kebab-case-3-to-5-words",
      "keep_segments": [
        {{"start": 12.34, "end": 28.91, "reason": "opening reframe"}},
        {{"start": 41.20, "end": 67.50, "reason": "supporting detail"}}
      ],
      "expected_duration_s": 42.7
    }}
  ]
}}

If the transcript contains no clip-worthy material, return {{"clips": []}}.
"""


def build_user_prompt(transcript: dict, max_clips: int = 1) -> str:
    """Build the user message with the transcript in word-aligned format."""
    lines = []
    current = []
    current_start = None
    for w in transcript["words"]:
        if current_start is None:
            current_start = w["start"]
        current.append(w["w"])
        # break on punctuation for readability
        if w["w"].endswith((".", "?", "!")) or len(current) >= 18:
            lines.append(f"[{current_start:.2f} > {w['end']:.2f}]  {' '.join(current)}")
            current = []
            current_start = None
    if current:
        lines.append(f"[{current_start:.2f} > {transcript['words'][-1]['end']:.2f}]  {' '.join(current)}")

    transcript_block = "\n".join(lines)
    return f"""# Source transcript ({transcript['duration']:.1f}s, {len(transcript['words'])} words, {transcript['language']})

Each line is a chunk with [start_sec > end_sec] timestamps. Use these timestamps verbatim
in your keep_segments. You may start or end a keep_segment at any word boundary inside a chunk:
look up the precise word's timestamp in the words array below.

{transcript_block}

# Word-level timestamps (use these for precise cuts)
{json.dumps(transcript['words'], ensure_ascii=False)}

# Task
Return up to {max_clips} of the strongest clips from this transcript, in JSON per the system schema.
Quality over quantity: return fewer clips rather than a weak one.
"""


def parse_response(raw: str) -> dict:
    """Pull the JSON object out of the model's reply, tolerating code fences."""
    raw = raw.strip()
    if raw.startswith("```"):
        raw = raw.split("\n", 1)[1] if "\n" in raw else ""
        raw = raw.rsplit("```", 1)[0].strip()
    start, end = raw.find("{"), raw.rfind("}")
    if start == -1 or end == -1:
        raise ValueError("the model did not return JSON")
    data = json.loads(raw[start:end + 1])
    if not isinstance(data.get("clips"), list):
        raise ValueError("the model's JSON has no 'clips' list")
    return data


def select_clips(transcript: dict, max_clips: int = 1) -> dict:
    try:
        import anthropic
    except ImportError:
        sys.exit(
            "The anthropic package is not installed. Run:\n"
            f"  {sys.executable} -m pip install -r {config.ROOT / 'requirements-optional.txt'}\n"
            "or skip this step: inside Claude Code, Claude can pick the clips itself."
        )
    if not (config.get("ANTHROPIC_API_KEY") or config.get("ANTHROPIC_AUTH_TOKEN")):
        sys.exit(
            "No ANTHROPIC_API_KEY is set (add it to config.env), so automatic picking "
            "cannot run. Inside Claude Code, Claude can pick the clips itself instead."
        )

    client = anthropic.Anthropic()
    user_prompt = build_user_prompt(transcript, max_clips=max_clips)

    print(f"[claude] selecting up to {max_clips} clip(s) from {transcript['duration']:.1f}s "
          f"transcript (model={config.ANTHROPIC_MODEL})")
    # Streamed so a long transcript cannot hit an HTTP timeout.
    with client.messages.stream(
        model=config.ANTHROPIC_MODEL,
        max_tokens=16000,
        system=build_system_prompt(),
        messages=[{"role": "user", "content": user_prompt}],
    ) as stream:
        msg = stream.get_final_message()

    if msg.stop_reason == "refusal":
        sys.exit("The model declined this transcript. Pick the clips by hand or in Claude Code.")
    if msg.stop_reason == "max_tokens":
        sys.exit("The model's answer was cut off. Ask for fewer clips and run again.")
    raw = "".join(b.text for b in msg.content if getattr(b, "type", "") == "text")
    return parse_response(raw)


def _usage(text: str) -> None:
    """Print usage. Asking for help is a success; missing arguments is an error."""
    asked = "--help" in sys.argv or "-h" in sys.argv
    print(text, file=sys.stdout if asked else sys.stderr)
    sys.exit(0 if asked else 2)


if __name__ == "__main__":
    if len(sys.argv) < 2 or sys.argv[1] in ("-h", "--help"):
        _usage("usage: python selector/select.py <transcript.json> [max_clips]")
    transcript_path = Path(sys.argv[1])
    max_clips = int(sys.argv[2]) if len(sys.argv) > 2 else 1
    transcript = json.loads(transcript_path.read_text(encoding="utf-8"))
    result = select_clips(transcript, max_clips=max_clips)
    print(json.dumps(result, indent=2))
