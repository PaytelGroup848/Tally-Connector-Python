"""
CtrlBooks - Automatic Field Matching & Suggestion Engine
----------------------------------------------------------------------
Analyzes source and target field schema specifications to generate safe mapping suggestions.
Outputs confidence levels (EXACT, HIGH, MEDIUM, LOW) and clear rationale without auto-activating.
"""

import re
from typing import Dict, Any, List
from shared.mapping.canonical_registry import canonical_registry

CONFIDENCE_EXACT = "EXACT"
CONFIDENCE_HIGH = "HIGH"
CONFIDENCE_MEDIUM = "MEDIUM"
CONFIDENCE_LOW = "LOW"

class FieldSuggestionEngine:
    @staticmethod
    def normalize_field_name(name: str) -> str:
        if not name:
            return ""
        return re.sub(r"[_\-\s]+", "", name.strip().lower())

    @classmethod
    def suggest_field_mappings(
        cls,
        canonical_entity_type: str,
        source_fields: List[Dict[str, Any]],
        target_fields: List[Dict[str, Any]]
    ) -> List[Dict[str, Any]]:
        suggestions = []
        c_fields = canonical_registry.get_canonical_fields(canonical_entity_type)

        mapped_targets = set()

        target_norm_map = {}
        for tf in target_fields:
            t_name = tf.get("field_name") or tf.get("name") or ""
            norm_t = cls.normalize_field_name(t_name)
            if norm_t:
                target_norm_map[norm_t] = tf

        for sf in source_fields:
            s_name = sf.get("field_name") or sf.get("name") or ""
            s_type = (sf.get("data_type") or "STRING").upper()
            norm_s = cls.normalize_field_name(s_name)

            if not norm_s:
                continue

            matched = False

            if norm_s in target_norm_map:
                tf = target_norm_map[norm_s]
                t_name = tf.get("field_name") or tf.get("name") or ""
                t_type = (tf.get("data_type") or "STRING").upper()
                suggestions.append({
                    "source_field": s_name,
                    "target_field": t_name,
                    "source_data_type": s_type,
                    "target_data_type": t_type,
                    "confidence": CONFIDENCE_EXACT,
                    "confidence_score": 1.0,
                    "suggested_transformation": "NONE",
                    "reason": f"Exact normalized name match ('{s_name}' == '{t_name}')"
                })
                mapped_targets.add(t_name)
                matched = True

            if not matched:
                for c_name, c_def in c_fields.items():
                    aliases = [cls.normalize_field_name(a) for a in c_def.get("aliases", [])]
                    aliases.append(cls.normalize_field_name(c_name))

                    if norm_s in aliases:
                        for tf in target_fields:
                            t_name = tf.get("field_name") or tf.get("name") or ""
                            norm_t = cls.normalize_field_name(t_name)
                            if norm_t in aliases and t_name not in mapped_targets:
                                t_type = (tf.get("data_type") or "STRING").upper()
                                suggestions.append({
                                    "source_field": s_name,
                                    "target_field": t_name,
                                    "source_data_type": s_type,
                                    "target_data_type": t_type,
                                    "confidence": CONFIDENCE_HIGH,
                                    "confidence_score": 0.85,
                                    "suggested_transformation": "NONE",
                                    "reason": f"Alias similarity match via canonical field '{c_name}'"
                                })
                                mapped_targets.add(t_name)
                                matched = True
                                break

            if not matched:
                for tf in target_fields:
                    t_name = tf.get("field_name") or tf.get("name") or ""
                    norm_t = cls.normalize_field_name(t_name)
                    if t_name in mapped_targets:
                        continue

                    if norm_s in norm_t or norm_t in norm_s:
                        t_type = (tf.get("data_type") or "STRING").upper()
                        suggestions.append({
                            "source_field": s_name,
                            "target_field": t_name,
                            "source_data_type": s_type,
                            "target_data_type": t_type,
                            "confidence": CONFIDENCE_MEDIUM,
                            "confidence_score": 0.65,
                            "suggested_transformation": "NONE",
                            "reason": f"Partial substring name match ('{norm_s}' and '{norm_t}')"
                        })
                        mapped_targets.add(t_name)
                        matched = True
                        break

        return suggestions

field_suggestion_engine = FieldSuggestionEngine()
