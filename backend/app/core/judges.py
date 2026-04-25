# backend/app/core/judges.py
import json
import re
import random
import logging
from typing import List, Dict, Optional
from app.db.models import ModelPreset
from app.core.generators import generate

logger = logging.getLogger(__name__)


MODEL_FAMILIES = {
    "openai": ["gpt-4", "gpt-4o", "gpt-4-turbo", "gpt-3.5", "o1", "o3", "o4"],
    "anthropic": ["claude-3", "claude-3.5", "claude-4"],
    "google": ["gemini", "gemma", "palm"],
    "mistral": ["mistral", "mixtral", "codestral", "pixtral"],
    "deepseek": ["deepseek"],
    "meta": ["llama"],
    "grok": ["grok"],
    "glm": ["glm", "chatglm"],
    "kimi": ["kimi", "moonshot"],
}


def _get_family(model_id: str) -> str | None:
    model_lower = model_id.lower()
    for family, prefixes in MODEL_FAMILIES.items():
        if any(model_lower.startswith(p) for p in prefixes):
            return family
    return None


def detect_family_overlap(judge_model_id: str, eval_model_ids: list[str]) -> list[dict]:
    warnings = []
    judge_family = _get_family(judge_model_id)
    if not judge_family:
        return warnings
    for model_id in eval_model_ids:
        if _get_family(model_id) == judge_family:
            warnings.append({
                "judge": judge_model_id,
                "model": model_id,
                "family": judge_family,
                "message": f"Warning: {judge_model_id} and {model_id} are from the same "
                           f"model family ({judge_family}). Research shows this can inflate "
                           f"scores by up to 23.6% on average (lin2025)."
            })
    return warnings


def build_scores_template(criteria: List[Dict], labels: List[str]) -> str:
    """
    Build a JSON template string with actual criteria names.

    Args:
        criteria: List of criterion dicts with 'name' key
        labels: List of response labels (e.g., ["A", "B", "C"])

    Returns:
        JSON template string with actual criteria names
    """
    criterion_names = [c["name"] for c in criteria]
    sample_scores = ", ".join([f'"{name}": 8' for name in criterion_names])

    label_templates = []
    for label in labels:
        label_templates.append(f'        "{label}": {{{sample_scores}}}')

    return "{\n" + ",\n".join(label_templates) + "\n    }"


def build_comments_template(labels: List[str]) -> str:
    """
    Build a JSON template for per-response comments.

    Args:
        labels: List of response labels (e.g., ["A", "B", "C"])

    Returns:
        JSON template string showing expected comment structure
    """
    label_templates = []
    for label in labels:
        label_templates.append(
            f'        "{label}": [{{"text": "specific observation", "sentiment": "positive"}}, '
            f'{{"text": "specific observation", "sentiment": "negative"}}]'
        )
    return "{\n" + ",\n".join(label_templates) + "\n    }"


def build_score_rationales_template(labels: List[str]) -> str:
    """
    Build a JSON template for per-response score rationales.

    Args:
        labels: List of response labels (e.g., ["A", "B", "C"])

    Returns:
        JSON template string showing expected score rationale structure
    """
    label_templates = []
    for label in labels:
        label_templates.append(f'        "{label}": "1-3 sentence rationale explaining the score"')
    return "{\n" + ",\n".join(label_templates) + "\n    }"


def remap_criterion_keys(scores: Dict, criteria: List[Dict]) -> Dict:
    """
    Remap criterionN keys to actual criteria names as fallback.

    Args:
        scores: Dict with possible criterionN keys
        criteria: List of criterion dicts with 'name' key

    Returns:
        Dict with actual criteria names
    """
    result = {}
    criterion_names = [c["name"] for c in criteria]

    for key, value in scores.items():
        # Check if key is criterionN pattern
        if key.startswith("criterion") and key[9:].isdigit():
            index = int(key[9:]) - 1  # criterion1 -> index 0
            if 0 <= index < len(criterion_names):
                result[criterion_names[index]] = value
            else:
                result[key] = value  # Keep original if out of bounds
        else:
            result[key] = value  # Keep existing names

    return result


def _repair_json(text: str) -> str:
    """Attempt to repair common JSON issues from LLM outputs."""
    # Remove multi-line comments (/* ... */)
    text = re.sub(r'/\*[\s\S]*?\*/', '', text)
    # Remove single-line comments (// ...) but NOT inside strings
    # Simple heuristic: only remove comments that start after a comma, brace, or newline
    text = re.sub(r'(?<=[\n,{}\[\]])\s*//[^\n]*', '', text)
    text = re.sub(r'^//[^\n]*', '', text, flags=re.MULTILINE)
    # Remove trailing commas before } or ]
    text = re.sub(r',\s*([\]}])', r'\1', text)
    # Replace NaN, Infinity, undefined with null
    text = re.sub(r'\bNaN\b', 'null', text)
    text = re.sub(r'-?Infinity\b', 'null', text)
    text = re.sub(r'\bundefined\b', 'null', text)
    # Quote unquoted property names: { key: "value" } → { "key": "value" }
    text = re.sub(r'(?<=[{,])\s*([a-zA-Z_]\w*)\s*:', r' "\1":', text)
    # Replace single quotes with double quotes (crude but handles simple cases)
    # Only if there are no double quotes at all (to avoid breaking valid JSON)
    if '"' not in text and "'" in text:
        text = text.replace("'", '"')
    # Remove control characters (except \n \r \t) that break JSON parsing
    text = re.sub(r'[\x00-\x08\x0b\x0c\x0e-\x1f]', '', text)
    return text


def _try_close_truncated_json(text: str) -> str:
    """Try to close truncated JSON by balancing braces and brackets."""
    # Step 1: Close any unterminated string
    in_string = False
    escape_next = False
    for c in text:
        if escape_next:
            escape_next = False
            continue
        if c == '\\' and in_string:
            escape_next = True
            continue
        if c == '"':
            in_string = not in_string

    if in_string:
        text += '"'

    # Step 2: Count open braces/brackets (now that strings are closed)
    open_braces = 0
    open_brackets = 0
    in_string = False
    escape_next = False
    for c in text:
        if escape_next:
            escape_next = False
            continue
        if c == '\\' and in_string:
            escape_next = True
            continue
        if c == '"':
            in_string = not in_string
            continue
        if in_string:
            continue
        if c == '{':
            open_braces += 1
        elif c == '}':
            open_braces -= 1
        elif c == '[':
            open_brackets += 1
        elif c == ']':
            open_brackets -= 1

    if open_braces <= 0 and open_brackets <= 0:
        return text  # Already balanced or over-closed

    # Remove trailing comma (common after truncation)
    text = re.sub(r',\s*$', '', text)

    # Step 3: Close brackets then braces
    for _ in range(max(0, open_brackets)):
        text += ']'
    for _ in range(max(0, open_braces)):
        text += '}'

    return text


def _loads(text: str) -> dict:
    """Parse JSON, converting NaN/Infinity to None."""
    return json.loads(text, parse_constant=lambda _: None)


def extract_json(text: str) -> dict:
    """
    Extract JSON from LLM response, handling markdown and text wrapping.

    Tries multiple strategies:
    1. Find JSON in markdown code block (```json ... ```)
    2. Find balanced braces (handles nested JSON)
    3. Repair common JSON issues and retry
    4. Close truncated JSON and retry
    5. Simple find as last resort

    Args:
        text: Raw LLM response text

    Returns:
        Parsed JSON dictionary

    Raises:
        ValueError: If no valid JSON found in response
    """
    if not text:
        raise ValueError("Empty response")

    # Try 1: Find JSON in markdown code block (case-insensitive language tag)
    code_block = re.search(r'```(?:json|JSON)?\s*(\{[\s\S]*?\})\s*```', text)
    if code_block:
        try:
            return _loads(code_block.group(1))
        except json.JSONDecodeError:
            # Try repairing the code block content
            try:
                return _loads(_repair_json(code_block.group(1)))
            except json.JSONDecodeError as e:
                logger.warning(f"Failed to parse JSON from markdown code block: {e}")

    # Try 2: Find balanced braces (handles nested JSON in explanatory text)
    # Collect all valid JSON candidates and return the largest one
    depth = 0
    start = None
    candidates = []
    failed_candidates = []  # Store for repair attempts
    for i, c in enumerate(text):
        if c == '{':
            if depth == 0:
                start = i
            depth += 1
        elif c == '}':
            depth -= 1
            if depth == 0 and start is not None:
                candidate_text = text[start:i+1]
                try:
                    parsed = _loads(candidate_text)
                    candidates.append((len(candidate_text), parsed))
                except json.JSONDecodeError:
                    failed_candidates.append(candidate_text)
                start = None

    # Return the largest valid JSON found
    if candidates:
        candidates.sort(reverse=True)  # Sort by size, largest first
        return candidates[0][1]

    # Try 3: Repair failed candidates (trailing commas, comments, unquoted keys, etc.)
    for candidate_text in sorted(failed_candidates, key=len, reverse=True):
        try:
            return _loads(_repair_json(candidate_text))
        except json.JSONDecodeError:
            continue

    # Try 4: Handle truncated JSON (model hit max tokens)
    # If we have an unclosed brace from balanced-brace scanning, try to close it
    if start is not None and depth > 0:
        truncated = text[start:]
        try:
            closed = _try_close_truncated_json(_repair_json(truncated))
            return _loads(closed)
        except (json.JSONDecodeError, ValueError) as e:
            logger.warning(f"Failed to recover truncated JSON: {e}")

    # Try 5: Last resort - simple find with repair
    json_start = text.find('{')
    json_end = text.rfind('}') + 1
    if json_start >= 0 and json_end > json_start:
        raw = text[json_start:json_end]
        try:
            return _loads(raw)
        except json.JSONDecodeError:
            try:
                return _loads(_repair_json(raw))
            except json.JSONDecodeError as e:
                logger.warning(f"Failed to parse JSON even after repair: {e}")

    # Try 6: If no closing brace found at all, try closing from the first opening brace
    if json_start >= 0 and json_end <= json_start:
        raw = text[json_start:]
        try:
            closed = _try_close_truncated_json(_repair_json(raw))
            return _loads(closed)
        except (json.JSONDecodeError, ValueError) as e:
            logger.warning(f"Failed to recover fully truncated JSON: {e}")

    raise ValueError("No valid JSON found in response")


SCORING_RUBRIC = '''
**Scoring Scale (use these definitions for all criteria):**
10 - Exemplary: Fully satisfies the criterion with no meaningful shortcomings. Could serve as a reference answer.
 9 - Excellent: Satisfies the criterion comprehensively. Any gaps are trivial and do not reduce usefulness.
 8 - Very Good: Satisfies the criterion with minor omissions or imprecisions that slightly limit quality.
 7 - Good: Largely satisfies the criterion. A few noticeable gaps but the core intent is met.
 6 - Competent: Satisfies the main aspects but has clear weaknesses or missing elements.
 5 - Adequate: Partially satisfies the criterion. Gets the basics right but lacks depth or precision.
 4 - Below Average: Attempts the criterion but misses important aspects. Useful only with caveats.
 3 - Poor: Minimally addresses the criterion. Significant errors, omissions, or misunderstandings.
 2 - Very Poor: Barely relates to the criterion. Mostly incorrect, irrelevant, or incoherent.
 1 - Failing: Does not address the criterion at all, or is completely wrong/incoherent.'''

COMPARISON_PROMPT = '''You are an expert evaluator. You will see responses from multiple AI models to the same prompt. The responses are presented in random order as numbered responses.

**Evaluation Criteria:**
{criteria}
''' + SCORING_RUBRIC + '''

**The Prompt:**
System: {system_prompt}
User: {user_prompt}

**Responses to Evaluate:**
{responses}

**Your Task:**
1. Rank all responses from best to worst using their blind labels (for example {blind_label_example})
2. Score each response on each criterion (1-10). Evaluate content quality independently of response length. A shorter response that fully addresses the criteria should score the same as a longer response with equivalent quality.
3. For each response, provide exactly 5 specific comments. Each comment is a concrete observation marked as either "positive" or "negative". The split is up to you based on quality.
4. For each response, provide `score_rationales` with 1-3 sentences explaining why that response received its score. Key these rationales by the response blind labels (for example {blind_label_example}).
5. Explain your ranking in 2-3 sentences

Respond in this exact JSON format with these specific criteria: {criterion_names}
{{
    "ranking": {label_list},
    "scores": {scores_template},
    "comments": {comments_template},
    "score_rationales": {score_rationales_template},
    "reasoning": "Response X wins because..."
}}'''

SEPARATE_PROMPT = '''You are an expert evaluator. Evaluate the following response.

**Evaluation Criteria:**
{criteria}
''' + SCORING_RUBRIC + '''

**The Prompt:**
System: {system_prompt}
User: {user_prompt}

**Response to Evaluate:**
{response}

**Your Task:**
1. Score this response on each criterion (1-10). Evaluate content quality independently of response length. A concise answer that fully addresses the criteria is equal to a verbose one of the same substance.
2. Provide exactly 5 specific comments. Each comment is a concrete observation marked as either "positive" or "negative". The split is up to you based on quality.
3. Explain your evaluation in 2-3 sentences

Respond in this exact JSON format with these specific criteria: {criterion_names}
{{
    "scores": {scores_template},
    "comments": [{{"text": "specific observation", "sentiment": "positive"}}, {{"text": "specific observation", "sentiment": "negative"}}],
    "score_rationale": "1-3 sentence rationale explaining the score",
    "reasoning": "This response excels at..."
}}'''

REFERENCE_ANSWER_SECTION = '''

**Reference Answer (for context):**
{expected_answer}

Note: Use this as a reference point, not as the only correct answer. Evaluate responses based on the criteria above.'''


def build_judge_prompt_comparison(
    system_prompt: str,
    user_prompt: str,
    criteria: List[Dict],
    responses_text: str,
    response_count: int,
    expected_answer: Optional[str] = None
) -> str:
    """Build the full judge prompt for comparison mode, optionally injecting a reference answer."""
    criteria_text = "\n".join([
        f"- {c['name']}: {c['description']} (weight: {c['weight']})"
        for c in criteria
    ])
    criterion_names = [c["name"] for c in criteria]
    blind_labels = [chr(ord("A") + i) for i in range(response_count)]
    blind_label_example = "/".join(blind_labels) if blind_labels else "A/B/C"
    scores_template = build_scores_template(criteria, blind_labels)
    comments_template = build_comments_template(blind_labels)
    score_rationales_template = build_score_rationales_template(blind_labels)
    label_list = json.dumps(blind_labels)
    criterion_names_str = ", ".join(criterion_names)

    prompt = COMPARISON_PROMPT.format(
        criteria=criteria_text,
        system_prompt=system_prompt,
        user_prompt=user_prompt,
        responses=responses_text,
        criterion_names=criterion_names_str,
        label_list=label_list,
        scores_template=scores_template,
        comments_template=comments_template,
        score_rationales_template=score_rationales_template,
        blind_label_example=blind_label_example
    )

    if expected_answer:
        prompt += REFERENCE_ANSWER_SECTION.format(expected_answer=expected_answer)

    return prompt


def build_judge_prompt_separate(
    system_prompt: str,
    user_prompt: str,
    criteria: List[Dict],
    response_text: str,
    expected_answer: Optional[str] = None
) -> str:
    """Build the full judge prompt for separate mode, optionally injecting a reference answer."""
    criteria_text = "\n".join([
        f"- {c['name']}: {c['description']} (weight: {c['weight']})"
        for c in criteria
    ])
    criterion_names = [c["name"] for c in criteria]
    criterion_names_str = ", ".join(criterion_names)
    sample_scores = ", ".join([f'"{name}": 8' for name in criterion_names])
    scores_template = f"{{{sample_scores}}}"

    prompt = SEPARATE_PROMPT.format(
        criteria=criteria_text,
        system_prompt=system_prompt,
        user_prompt=user_prompt,
        response=response_text,
        criterion_names=criterion_names_str,
        scores_template=scores_template
    )

    if expected_answer:
        prompt += REFERENCE_ANSWER_SECTION.format(expected_answer=expected_answer)

    return prompt


def create_blind_mapping(model_ids: List[int]) -> Dict[str, int]:
    """Shuffle model IDs and assign to A, B, C, etc."""
    shuffled = model_ids.copy()
    random.shuffle(shuffled)
    labels = "ABCDEFGHIJKLMNOPQRSTUVWXYZ"  # Up to 26 models
    return {labels[i]: mid for i, mid in enumerate(shuffled)}


def _build_comparison_responses(
    generations: Dict[int, str],
    blind_mapping: Dict[str, int],
) -> tuple[str, Dict[str, str]]:
    """
    Build response text with randomized presentation order.

    The blind_mapping assigns models to A/B/C labels (for result tracking).
    This function independently randomizes the ORDER in which responses are
    PRESENTED to the judge (as "Response 1", "Response 2", etc.), decoupling
    presentation position from blind label assignment.

    Returns:
        (formatted_text, presentation_to_blind_mapping)
        presentation_to_blind_mapping maps "1"/"2"/"3" to "A"/"B"/"C"
    """
    reverse_mapping = {v: k for k, v in blind_mapping.items()}

    # Create list of (blind_label, model_id, content) and shuffle for presentation
    items = [(reverse_mapping[mid], mid, content) for mid, content in generations.items()]
    random.shuffle(items)  # Randomize presentation order

    # Build presentation: "Response 1", "Response 2", etc.
    responses_parts = []
    presentation_to_blind = {}  # "1" -> "A", "2" -> "B", etc.

    for i, (blind_label, mid, content) in enumerate(items):
        pres_label = str(i + 1)
        presentation_to_blind[pres_label] = blind_label
        responses_parts.append(f"**Response {pres_label} ({blind_label}):**\n{content}")

    return "\n\n".join(responses_parts), presentation_to_blind


async def judge_comparison(
    judge_preset: ModelPreset,
    system_prompt: str,
    user_prompt: str,
    generations: Dict[int, str],  # {model_id: content}
    criteria: List[Dict],  # [{name, description, weight}]
    temperature: float = 0.7,
    expected_answer: Optional[str] = None
) -> dict:
    """
    Judge multiple responses in comparison mode.

    Returns:
        {
            "success": bool,
            "blind_mapping": {"A": model_id, "B": model_id, ...},
            "rankings": ["A", "B", "C"],
            "scores": {model_id: {criterion: score}},
            "reasoning": str,
            "error": str (if failed)
        }
    """
    # Create blind mapping (model_id -> A/B/C)
    model_ids = list(generations.keys())
    blind_mapping = create_blind_mapping(model_ids)
    # Randomize presentation order (independent of blind labels)
    responses_text, presentation_to_blind = _build_comparison_responses(
        generations, blind_mapping
    )

    prompt = build_judge_prompt_comparison(
        system_prompt=system_prompt,
        user_prompt=user_prompt,
        criteria=criteria,
        responses_text=responses_text,
        response_count=len(model_ids),
        expected_answer=expected_answer
    )

    result = await generate(judge_preset, "You are an expert evaluator.", prompt, temperature=temperature, json_mode=True)

    if not result["success"]:
        return {"success": False, "error": result["error"]}

    try:
        content = result["content"]
        try:
            data = extract_json(content)
        except ValueError:
            # Fallback: thinking models may put JSON in thinking parts
            full_content = result.get("full_content")
            if full_content:
                logger.warning("JSON not found in answer, trying full_content (thinking + answer)")
                data = extract_json(full_content)
            else:
                raise

        # Validate ranking is an exact permutation of blind labels.
        valid_blind_labels = set(blind_mapping.keys())
        rankings_raw = data["ranking"]
        rankings_str = [str(r).strip().upper() for r in rankings_raw]

        if len(rankings_str) != len(valid_blind_labels):
            return {
                "success": False,
                "error": f"Judge returned {len(rankings_str)} rankings, "
                         f"expected exactly {len(valid_blind_labels)}"
            }
        if len(set(rankings_str)) != len(rankings_str):
            duplicates = [r for r in rankings_str if rankings_str.count(r) > 1]
            return {
                "success": False,
                "error": f"Judge returned duplicate rankings {list(set(duplicates))}, "
                         f"each response must be ranked exactly once"
            }
        if set(rankings_str) != valid_blind_labels:
            return {
                "success": False,
                "error": f"Judge returned rankings {sorted(rankings_str)}, "
                         f"expected exactly {sorted(valid_blind_labels)}"
            }

        def _normalize_blind_label(label: object) -> str:
            return str(label).strip().upper()

        def _remap_blind_labeled_field(field_name: str, raw_value: object) -> dict:
            if raw_value is None:
                raise ValueError(f"Judge response missing required {field_name} field")
            if not isinstance(raw_value, dict):
                raise ValueError(f"Judge response {field_name} must be an object keyed by blind labels")

            normalized_items = {}
            for label, value in raw_value.items():
                normalized_label = _normalize_blind_label(label)
                if normalized_label in normalized_items:
                    raise ValueError(
                        f"Judge response {field_name} contains duplicate labels after normalization: {normalized_label}"
                    )
                normalized_items[normalized_label] = value

            key_labels = set(normalized_items.keys())
            if key_labels != valid_blind_labels:
                missing_labels = sorted(valid_blind_labels - key_labels)
                unknown_labels = sorted(key_labels - valid_blind_labels)
                parts = []
                if missing_labels:
                    parts.append(f"missing labels {missing_labels}")
                if unknown_labels:
                    parts.append(f"unknown labels {unknown_labels}")
                raise ValueError(
                    f"Judge response {field_name} must contain exactly the blind labels: " + ", ".join(parts)
                )

            remapped = {}
            for blind_label, value in normalized_items.items():
                remapped[blind_mapping[blind_label]] = value
            return remapped

        # Map blind-labeled fields directly to model IDs.
        scores_by_model = {
            model_id: remap_criterion_keys(label_scores, criteria)
            for model_id, label_scores in _remap_blind_labeled_field("scores", data.get("scores")).items()
        }
        comments_by_model = _remap_blind_labeled_field("comments", data.get("comments"))
        rankings_blind = [_normalize_blind_label(r) for r in rankings_raw]
        score_rationales_by_model = _remap_blind_labeled_field(
            "score_rationales",
            data.get("score_rationales")
        )

        return {
            "success": True,
            "blind_mapping": blind_mapping,
            "presentation_mapping": presentation_to_blind,
            "rankings": rankings_blind,
            "scores": scores_by_model,
            "comments": comments_by_model,
            "score_rationales": score_rationales_by_model,
            "reasoning": data.get("reasoning", ""),
            "latency_ms": result.get("latency_ms"),
            "tokens": result.get("tokens"),
            "temperature": temperature
        }

    except Exception as e:
        raw = result.get("content", "")[:500]
        full = (result.get("full_content") or "")[:500]
        logger.error(
            f"Parse error (comparison): {e} | thinking_only={result.get('thinking_only', False)} "
            f"| content[:{len(result.get('content', ''))}]: {raw} "
            f"| full_content[:{len(result.get('full_content') or '')}]: {full}"
        )
        return {"success": False, "error": f"Parse error: {str(e)}"}


async def judge_separate(
    judge_preset: ModelPreset,
    system_prompt: str,
    user_prompt: str,
    content: str,
    criteria: List[Dict],
    temperature: float = 0.7,
    expected_answer: Optional[str] = None
) -> dict:
    """
    Judge a single response independently.

    Returns:
        {
            "success": bool,
            "scores": {criterion: score},
            "reasoning": str,
            "error": str (if failed)
        }
    """
    prompt = build_judge_prompt_separate(
        system_prompt=system_prompt,
        user_prompt=user_prompt,
        criteria=criteria,
        response_text=content,
        expected_answer=expected_answer
    )

    result = await generate(judge_preset, "You are an expert evaluator.", prompt, temperature=temperature, json_mode=True)

    if not result["success"]:
        return {"success": False, "error": result["error"]}

    try:
        # Parse JSON from response using robust extractor
        content = result["content"]
        try:
            data = extract_json(content)
        except ValueError:
            # Fallback: thinking models may put JSON in thinking parts
            full_content = result.get("full_content")
            if full_content:
                logger.warning("JSON not found in answer, trying full_content (thinking + answer)")
                data = extract_json(full_content)
            else:
                raise

        if "score_rationales" in data:
            return {
                "success": False,
                "error": "Judge response score_rationales is not allowed in separate mode; use singular score_rationale"
            }

        score_rationale = data.get("score_rationale")
        if not isinstance(score_rationale, str) or not score_rationale.strip():
            return {
                "success": False,
                "error": "Judge response missing required non-blank score_rationale field"
            }

        # Remap criterionN keys to actual names as fallback
        remapped_scores = remap_criterion_keys(data["scores"], criteria)
        comments = data.get("comments", [])

        return {
            "success": True,
            "scores": remapped_scores,
            "comments": comments,
            "score_rationale": score_rationale.strip(),
            "reasoning": data.get("reasoning", ""),
            "latency_ms": result.get("latency_ms"),
            "tokens": result.get("tokens"),
            "temperature": temperature
        }

    except Exception as e:
        raw = result.get("content", "")[:500]
        logger.error(f"Parse error: {e} | Raw content (first 500 chars): {raw}")
        return {"success": False, "error": f"Parse error: {str(e)}"}


SUMMARIZE_PROMPT = '''You evaluated multiple AI models. Here are all your specific comments across several questions:

{comments_text}

For each model, produce a structured summary. Be concise — state patterns, don't repeat every example.

Respond in this exact JSON format:
{{
{model_templates}
}}'''


async def summarize_judge_comments(
    judge_preset: ModelPreset,
    comments_by_model: Dict[str, list],  # {model_name: [{text, sentiment}]}
) -> dict:
    """
    Summarize all judge comments per model into concise qualitative feedback.

    Args:
        judge_preset: The judge model preset to use for summarization
        comments_by_model: {model_name: [{text, sentiment}, ...]}

    Returns:
        {success: bool, summaries: {model_name: "summary text"}, error: str}
    """
    if not comments_by_model:
        return {"success": True, "summaries": {}}

    # Format comments for the prompt
    sections = []
    for model_name, comments in comments_by_model.items():
        positive = [c["text"] for c in comments if c.get("sentiment") == "positive"]
        negative = [c["text"] for c in comments if c.get("sentiment") == "negative"]
        section = f"**{model_name}:**\n"
        if positive:
            section += "  Strengths: " + "; ".join(positive) + "\n"
        if negative:
            section += "  Weaknesses: " + "; ".join(negative) + "\n"
        section += f"  ({len(positive)} positive, {len(negative)} negative out of {len(comments)} total)"
        sections.append(section)

    comments_text = "\n\n".join(sections)
    model_names = list(comments_by_model.keys())
    model_templates = ",\n".join([
        f'    "{name}": {{"verdict": "one sentence overall", "strengths": ["point", "point"], "weaknesses": ["point", "point"]}}'
        for name in model_names
    ])

    prompt = SUMMARIZE_PROMPT.format(
        comments_text=comments_text,
        model_templates=model_templates
    )

    result = await generate(
        judge_preset,
        "You are an expert at synthesizing evaluation feedback into concise summaries.",
        prompt,
        temperature=0.3,
        timeout=60.0,
        json_mode=True
    )

    if not result["success"]:
        return {"success": False, "error": result["error"]}

    try:
        try:
            data = extract_json(result["content"])
        except ValueError:
            full_content = result.get("full_content")
            if full_content:
                logger.warning("JSON not found in answer, trying full_content (thinking + answer)")
                data = extract_json(full_content)
            else:
                raise
        # Validate we got summaries for at least some models
        summaries = {}
        for model_name in model_names:
            if model_name in data:
                summaries[model_name] = data[model_name]
        return {"success": True, "summaries": summaries, "tokens": result.get("tokens")}
    except Exception as e:
        raw = result.get("content", "")[:500]
        logger.error(f"Parse error: {e} | Raw content (first 500 chars): {raw}")
        return {"success": False, "error": f"Parse error: {str(e)}"}
