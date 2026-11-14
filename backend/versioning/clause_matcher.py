"""
clause_matcher.py

Hybrid clause matching engine for version-aware incremental graph maintenance.
Combines exact fingerprint matching, identifier tracking, and text similarity
to detect unchanged, modified, renumbered, split, merged, and ambiguous clauses.
"""

from dataclasses import dataclass, field
import difflib
from enum import Enum
import re
from typing import List, Dict, Optional, Tuple, Set, Any

from .version_manager import VersionedClause, normalize_clause_text


class MatchConfidence(str, Enum):
    CERTAIN = "certain"
    HIGH = "high"
    PROBABLE = "probable"
    AMBIGUOUS = "ambiguous"
    NONE = "none"


class MatchType(str, Enum):
    EXACT_UNCHANGED = "exact_unchanged"
    IN_PLACE_MODIFIED = "in_place_modified"
    RENUMBERED_UNCHANGED = "renumbered_unchanged"
    RENUMBERED_MODIFIED = "renumbered_modified"
    SPLIT_SOURCE = "split_source"
    MERGE_TARGET = "merge_target"
    AMBIGUOUS = "ambiguous"
    UNMATCHED = "unmatched"


@dataclass
class MatchResult:
    """
    Result of comparing an old clause against a new clause.
    """
    old_clause: Optional[VersionedClause]
    new_clause: Optional[VersionedClause]
    match_type: MatchType
    confidence: MatchConfidence
    similarity_score: float
    notes: str = ""
    candidate_matches: List[Tuple[str, float]] = field(default_factory=list)


def tokenize_text(text: str) -> List[str]:
    """Tokenizes text into normalized alphanumeric words."""
    norm = normalize_clause_text(text)
    return re.findall(r'\b[a-z0-9]+\b', norm)


def compute_token_jaccard(text1: str, text2: str) -> float:
    """Computes Jaccard similarity between token sets of two texts."""
    tokens1 = set(tokenize_text(text1))
    tokens2 = set(tokenize_text(text2))
    if not tokens1 and not tokens2:
        return 1.0
    if not tokens1 or not tokens2:
        return 0.0
    intersection = len(tokens1 & tokens2)
    union = len(tokens1 | tokens2)
    return intersection / union if union > 0 else 0.0


def compute_sequence_similarity(text1: str, text2: str) -> float:
    """Computes Ratcliff-Obershelp sequence similarity ratio using difflib."""
    norm1 = normalize_clause_text(text1)
    norm2 = normalize_clause_text(text2)
    if not norm1 and not norm2:
        return 1.0
    if not norm1 or not norm2:
        return 0.0
    len1, len2 = len(norm1), len(norm2)
    if len1 / max(len2, 1) > 4.0 or len2 / max(len1, 1) > 4.0:
        return 0.0
    return difflib.SequenceMatcher(None, norm1, norm2).ratio()


def compute_text_similarity(text1: str, text2: str) -> float:
    """
    Hybrid text similarity metric combining token Jaccard and sequence matching.
    Gives a balanced score reflecting both vocabulary overlap and structural phrasing.
    """
    if not text1 and not text2:
        return 1.0
    if not text1 or not text2:
        return 0.0

    jaccard = compute_token_jaccard(text1, text2)
    if jaccard < 0.15:
        return round(jaccard * 0.5, 4)

    seq_sim = compute_sequence_similarity(text1, text2)
    return round(0.4 * jaccard + 0.6 * seq_sim, 4)


class ClauseMatcher:
    """
    Compares clauses from an old document version against clauses from a new document version.
    """

    def __init__(
        self,
        in_place_similarity_threshold: float = 0.35,
        high_in_place_threshold: float = 0.85,
        renumbered_similarity_threshold: float = 0.70,
        ambiguity_delta_threshold: float = 0.08,
        split_merge_threshold: float = 0.75,
    ):
        self.in_place_similarity_threshold = in_place_similarity_threshold
        self.high_in_place_threshold = high_in_place_threshold
        self.renumbered_similarity_threshold = renumbered_similarity_threshold
        self.ambiguity_delta_threshold = ambiguity_delta_threshold
        self.split_merge_threshold = split_merge_threshold

    def match(
        self,
        old_clauses: List[VersionedClause],
        new_clauses: List[VersionedClause]
    ) -> Dict[str, Any]:
        """
        Executes multi-pass hybrid matching across old and new clauses.
        Returns:
        - matches: List[MatchResult] for 1-to-1 matches
        - splits: List[Dict] for 1-to-N detected splits
        - merges: List[Dict] for N-to-1 detected merges
        - unmatched_old: List[VersionedClause] (candidates for deletion)
        - unmatched_new: List[VersionedClause] (candidates for addition)
        - ambiguous: List[MatchResult] flagged for manual review
        """
        matched_old_ids: Set[str] = set()
        matched_new_ids: Set[str] = set()
        matches: List[MatchResult] = []
        ambiguous_matches: List[MatchResult] = []
        splits: List[Dict[str, Any]] = []
        merges: List[Dict[str, Any]] = []

        old_by_raw_id: Dict[str, List[VersionedClause]] = {}
        for c in old_clauses:
            old_by_raw_id.setdefault(c.clause_id, []).append(c)

        old_by_fingerprint: Dict[str, List[VersionedClause]] = {}
        for c in old_clauses:
            old_by_fingerprint.setdefault(c.text_fingerprint, []).append(c)

        # -------------------------------------------------------------
        # PASS 1: Exact matches (Same identifier + Exact text hash)
        # -------------------------------------------------------------
        for new_c in new_clauses:
            if new_c.clause_id in old_by_raw_id:
                candidates = old_by_raw_id[new_c.clause_id]
                for old_c in candidates:
                    if old_c.stable_clause_id in matched_old_ids:
                        continue
                    if old_c.text_fingerprint == new_c.text_fingerprint:
                        matches.append(MatchResult(
                            old_clause=old_c,
                            new_clause=new_c,
                            match_type=MatchType.EXACT_UNCHANGED,
                            confidence=MatchConfidence.CERTAIN,
                            similarity_score=1.0,
                            notes="Exact clause ID and exact text fingerprint match.",
                        ))
                        matched_old_ids.add(old_c.stable_clause_id)
                        matched_new_ids.add(new_c.stable_clause_id)
                        break

        # -------------------------------------------------------------
        # PASS 2: High-confidence in-place modifications (sim >= high_in_place_threshold)
        # Same clause ID, minor wording changes that are clearly the same clause
        # -------------------------------------------------------------
        for new_c in new_clauses:
            if new_c.stable_clause_id in matched_new_ids:
                continue
            if new_c.clause_id in old_by_raw_id:
                candidates = [
                    c for c in old_by_raw_id[new_c.clause_id]
                    if c.stable_clause_id not in matched_old_ids
                ]
                if len(candidates) == 1:
                    old_c = candidates[0]
                    sim = compute_text_similarity(old_c.text, new_c.text)
                    if sim >= self.high_in_place_threshold:
                        matches.append(MatchResult(
                            old_clause=old_c,
                            new_clause=new_c,
                            match_type=MatchType.IN_PLACE_MODIFIED,
                            confidence=MatchConfidence.HIGH,
                            similarity_score=sim,
                            notes=f"Same clause ID '{new_c.clause_id}' with high similarity ({sim:.2f}).",
                        ))
                        matched_old_ids.add(old_c.stable_clause_id)
                        matched_new_ids.add(new_c.stable_clause_id)

        # -------------------------------------------------------------
        # PASS 3: Detect Clause Splitting (1 old -> N adjacent new)
        # -------------------------------------------------------------
        for old_c in old_clauses:
            if old_c.stable_clause_id in matched_old_ids:
                continue
            unmatched_new = [c for c in new_clauses if c.stable_clause_id not in matched_new_ids]
            if len(unmatched_new) < 2:
                continue

            for i in range(len(unmatched_new)):
                for j in range(i + 2, min(i + 5, len(unmatched_new) + 1)):
                    sub_new = unmatched_new[i:j]
                    combined_text = " ".join(c.text for c in sub_new)
                    sim = compute_text_similarity(old_c.text, combined_text)
                    max_single_sim = max(compute_text_similarity(old_c.text, c.text) for c in sub_new)
                    if sim >= self.split_merge_threshold and (sim > max_single_sim + 0.15 or sim >= 0.85):
                        splits.append({
                            "old_clause": old_c,
                            "target_new_clauses": sub_new,
                            "similarity_score": sim,
                            "notes": f"Old clause '{old_c.clause_id}' split into new clauses: {[c.clause_id for c in sub_new]}.",
                        })
                        matched_old_ids.add(old_c.stable_clause_id)
                        for c in sub_new:
                            matched_new_ids.add(c.stable_clause_id)
                        break
                if old_c.stable_clause_id in matched_old_ids:
                    break

        # -------------------------------------------------------------
        # PASS 4: Detect Clause Merging (N adjacent old -> 1 new)
        # -------------------------------------------------------------
        for new_c in new_clauses:
            if new_c.stable_clause_id in matched_new_ids:
                continue
            unmatched_old = [c for c in old_clauses if c.stable_clause_id not in matched_old_ids]
            if len(unmatched_old) < 2:
                continue

            for i in range(len(unmatched_old)):
                for j in range(i + 2, min(i + 5, len(unmatched_old) + 1)):
                    sub_old = unmatched_old[i:j]
                    combined_text = " ".join(c.text for c in sub_old)
                    sim = compute_text_similarity(combined_text, new_c.text)
                    max_single_sim = max(compute_text_similarity(c.text, new_c.text) for c in sub_old)
                    if sim >= self.split_merge_threshold and (sim > max_single_sim + 0.15 or sim >= 0.85):
                        merges.append({
                            "source_old_clauses": sub_old,
                            "target_new_clause": new_c,
                            "similarity_score": sim,
                            "notes": f"Old clauses {[c.clause_id for c in sub_old]} merged into new clause '{new_c.clause_id}'.",
                        })
                        matched_new_ids.add(new_c.stable_clause_id)
                        for c in sub_old:
                            matched_old_ids.add(c.stable_clause_id)
                        break
                if new_c.stable_clause_id in matched_new_ids:
                    break

        # -------------------------------------------------------------
        # PASS 5: Moderate-confidence in-place modifications
        # -------------------------------------------------------------
        for new_c in new_clauses:
            if new_c.stable_clause_id in matched_new_ids:
                continue

            if new_c.clause_id in old_by_raw_id:
                candidates = [
                    c for c in old_by_raw_id[new_c.clause_id]
                    if c.stable_clause_id not in matched_old_ids
                ]
                if len(candidates) == 1:
                    old_c = candidates[0]
                    sim = compute_text_similarity(old_c.text, new_c.text)
                    if sim >= self.in_place_similarity_threshold:
                        matches.append(MatchResult(
                            old_clause=old_c,
                            new_clause=new_c,
                            match_type=MatchType.IN_PLACE_MODIFIED,
                            confidence=MatchConfidence.HIGH if sim >= 0.6 else MatchConfidence.PROBABLE,
                            similarity_score=sim,
                            notes=f"Same clause ID '{new_c.clause_id}' with modified content (similarity: {sim:.2f}).",
                        ))
                        matched_old_ids.add(old_c.stable_clause_id)
                        matched_new_ids.add(new_c.stable_clause_id)
                elif len(candidates) > 1:
                    best_match = None
                    best_sim = -1.0
                    for old_c in candidates:
                        context_bonus = 0.1 if (old_c.section and old_c.section == new_c.section) else 0.0
                        sim = compute_text_similarity(old_c.text, new_c.text) + context_bonus
                        if sim > best_sim:
                            best_sim = sim
                            best_match = old_c

                    if best_match and best_sim >= self.in_place_similarity_threshold:
                        matches.append(MatchResult(
                            old_clause=best_match,
                            new_clause=new_c,
                            match_type=MatchType.IN_PLACE_MODIFIED,
                            confidence=MatchConfidence.HIGH if best_sim >= 0.6 else MatchConfidence.PROBABLE,
                            similarity_score=min(best_sim, 1.0),
                            notes=f"Disambiguated repeated clause ID '{new_c.clause_id}' by similarity/context.",
                        ))
                        matched_old_ids.add(best_match.stable_clause_id)
                        matched_new_ids.add(new_c.stable_clause_id)

        # -------------------------------------------------------------
        # PASS 6: Renumbered Clauses with Exact Content (Fingerprint match)
        # -------------------------------------------------------------
        for new_c in new_clauses:
            if new_c.stable_clause_id in matched_new_ids:
                continue

            if new_c.text_fingerprint in old_by_fingerprint:
                candidates = [
                    c for c in old_by_fingerprint[new_c.text_fingerprint]
                    if c.stable_clause_id not in matched_old_ids
                ]
                if len(candidates) == 1:
                    old_c = candidates[0]
                    matches.append(MatchResult(
                        old_clause=old_c,
                        new_clause=new_c,
                        match_type=MatchType.RENUMBERED_UNCHANGED,
                        confidence=MatchConfidence.HIGH,
                        similarity_score=1.0,
                        notes=f"Identical text relocated from clause '{old_c.clause_id}' to '{new_c.clause_id}'.",
                    ))
                    matched_old_ids.add(old_c.stable_clause_id)
                    matched_new_ids.add(new_c.stable_clause_id)

        # -------------------------------------------------------------
        # PASS 7: Renumbered Clauses with Modified Content / Ambiguity Check
        # -------------------------------------------------------------
        remaining_old = [c for c in old_clauses if c.stable_clause_id not in matched_old_ids]
        remaining_new = [c for c in new_clauses if c.stable_clause_id not in matched_new_ids]

        for new_c in remaining_new:
            if new_c.stable_clause_id in matched_new_ids:
                continue

            candidate_scores = []
            for old_c in remaining_old:
                if old_c.stable_clause_id in matched_old_ids:
                    continue
                sim = compute_text_similarity(old_c.text, new_c.text)
                if sim >= self.renumbered_similarity_threshold:
                    candidate_scores.append((old_c, sim))

            if not candidate_scores:
                continue

            candidate_scores.sort(key=lambda x: x[1], reverse=True)
            top_match, top_sim = candidate_scores[0]

            if len(candidate_scores) > 1:
                second_match, second_sim = candidate_scores[1]
                if abs(top_sim - second_sim) < self.ambiguity_delta_threshold:
                    amb_record = MatchResult(
                        old_clause=top_match,
                        new_clause=new_c,
                        match_type=MatchType.AMBIGUOUS,
                        confidence=MatchConfidence.AMBIGUOUS,
                        similarity_score=top_sim,
                        notes=f"Ambiguous match between '{new_c.clause_id}' and multiple old clauses ({top_match.clause_id}: {top_sim:.2f}, {second_match.clause_id}: {second_sim:.2f}).",
                        candidate_matches=[(c[0].clause_id, round(c[1], 3)) for c in candidate_scores[:3]]
                    )
                    ambiguous_matches.append(amb_record)
                    continue

            matches.append(MatchResult(
                old_clause=top_match,
                new_clause=new_c,
                match_type=MatchType.RENUMBERED_MODIFIED,
                confidence=MatchConfidence.PROBABLE if top_sim < 0.85 else MatchConfidence.HIGH,
                similarity_score=top_sim,
                notes=f"Clause renumbered from '{top_match.clause_id}' to '{new_c.clause_id}' with text similarity {top_sim:.2f}.",
            ))
            matched_old_ids.add(top_match.stable_clause_id)
            matched_new_ids.add(new_c.stable_clause_id)

        final_unmatched_old = [c for c in old_clauses if c.stable_clause_id not in matched_old_ids]
        final_unmatched_new = [c for c in new_clauses if c.stable_clause_id not in matched_new_ids]

        return {
            "matches": matches,
            "splits": splits,
            "merges": merges,
            "unmatched_old": final_unmatched_old,
            "unmatched_new": final_unmatched_new,
            "ambiguous": ambiguous_matches,
        }
