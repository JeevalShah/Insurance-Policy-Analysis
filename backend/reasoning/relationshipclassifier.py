import json
import re
import logging
import ollama
from typing import List, Dict, Any

logger = logging.getLogger(__name__)

NOT_RELATED_LABEL = "NOT_RELATED"
BATCH_LABELS = {"CONFLICT", "COMPLIANT", "SUPPORTING", "REDUNDANT", NOT_RELATED_LABEL}


def _extract_json_array(text: str) -> str:
    """Extracts JSON array content even if wrapped in markdown code fences or preambles."""
    if not isinstance(text, str):
        text = str(text)
        
    clean_text = re.sub(r"^```(?:json)?\s*|\s*```$", "", text.strip(), flags=re.MULTILINE)
    match = re.search(r"(\{.*\}|\[.*\])", clean_text, re.DOTALL)
    if match:
        return match.group(1)
    return clean_text


def _extract_response_content(response: Any) -> str:
    """Safely extracts text content from dicts, mock objects, or raw strings returned by fake_ollama."""
    if isinstance(response, dict):
        msg = response.get("message", {})
        if isinstance(msg, dict):
            return msg.get("content", "")
        return str(msg)
    elif hasattr(response, "message"):
        msg = getattr(response, "message")
        if hasattr(msg, "content"):
            return getattr(msg, "content")
        return str(msg)
    elif isinstance(response, str):
        return response
    return str(response)


def classify_relationship(
    trigger: str,
    clause_text: str,
    model: str = "llama3",
) -> str:
    """Classifies a single candidate clause against a regulatory trigger."""
    prompt = f"""You are an insurance compliance expert.

Regulatory Trigger:
{trigger}

Policy Clause:
{clause_text}

Classify the relationship of the policy clause to the regulatory trigger as exactly one of:
CONFLICT, COMPLIANT, SUPPORTING, REDUNDANT, NOT_RELATED.

Return ONLY the single classification label as plain text."""

    try:
        response = ollama.chat(
            model=model,
            messages=[{"role": "user", "content": prompt}],
            options={"temperature": 0.0},
        )
        content = _extract_response_content(response)
        raw_label = str(content).strip().upper()
        
        for lbl in BATCH_LABELS:
            if lbl in raw_label:
                return lbl
        return raw_label if raw_label else "UNKNOWN"
    except Exception as e:
        logger.error(f"Single relationship classification failed: {e}")
        return "UNKNOWN"

def classify_relationship_batch(
    trigger: str,
    candidates: List[Dict[str, Any]],
    model: str = "llama3",
    chunk_size: int = 4,  # Adjust chunk size to stay safely within token limits
) -> Dict[str, str]:
    if not candidates:
        return {}

    # Truncate trigger if it is excessively long
    truncated_trigger = trigger[:1500] + "..." if len(trigger) > 1500 else trigger

    # Helper function to process a single sub-batch
    def _process_chunk(chunk: List[Dict[str, Any]]) -> Dict[str, str]:
        candidate_map = {}
        blocks = []
        for c in chunk:
            cid = str(c.get("clause_id", c.get("id", ""))).strip()
            if cid:
                candidate_map[cid] = cid
                # Truncate clause text to fit context bounds
                raw_text = c.get("text", "")
                text = raw_text[:1000] + "..." if len(raw_text) > 1000 else raw_text
                blocks.append(f"[{cid}]\nClause ID: {cid}\nText: {text}")
        candidates_block = "\n\n".join(blocks)
        
        prompt = f"""You are an insurance compliance expert.
Regulatory Trigger: {truncated_trigger}

Candidate Policy Clauses:
{candidates_block}

Classify each clause as CONFLICT, COMPLIANT, SUPPORTING, REDUNDANT, or NOT_RELATED. 
Return ONLY a JSON array of objects:
[
  {{"clause_id": "<id>", "relationship": "<LABEL>"}}
]

Output ONLY valid, raw JSON. Do not include markdown backticks (```), explanations, or conversational filler. Your entire response must be parsable by json.loads."""

        try:
            response = ollama.chat(
                model=model,
                messages=[{"role": "user", "content": prompt}],
                format="json",
                options={"temperature": 0.0, "num_ctx": 4096},
            )

            raw_content = _extract_response_content(response)
            json_str = _extract_json_array(raw_content)
            parsed = json.loads(json_str)

            if not isinstance(parsed, list):
                raise ValueError("Parsed batch output is not a list.")

            chunk_results: Dict[str, str] = {}
            for entry in parsed:
                if not isinstance(entry, dict):
                    continue

                raw_id = str(entry.get("clause_id", "")).strip()
                matched_id = candidate_map.get(raw_id)
                if not matched_id:
                    continue

                label = str(entry.get("relationship", "")).strip().upper()
                matched_label = next((lbl for lbl in BATCH_LABELS if lbl in label), label)
                chunk_results[matched_id] = matched_label

            for norm_id, orig_id in candidate_map.items():
                if orig_id not in chunk_results:
                    chunk_results[orig_id] = NOT_RELATED_LABEL

            return chunk_results

        except Exception as e:
            logger.error(f"Chunk classification failed ({e}); falling back to per-candidate calls.")
            fallback: Dict[str, str] = {}
            for c in chunk:
                cid_str = str(c.get("clause_id", c.get("id", "")))
                fallback[cid_str] = classify_relationship(truncated_trigger, c.get("text", ""), model=model)
            return fallback

    # Run chunks sequentially and combine results
    all_results: Dict[str, str] = {}
    for i in range(0, len(candidates), chunk_size):
        sub_batch = candidates[i : i + chunk_size]
        all_results.update(_process_chunk(sub_batch))

    return all_results