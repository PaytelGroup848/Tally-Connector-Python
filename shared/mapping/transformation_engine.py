"""
CtrlBooks - Transformation Engine
---------------------------------------------
Controlled, isolated field value transformation engine supporting 13 allow-listed transformation types.
Strictly prohibits code evaluation (eval/exec/shell execution) for enterprise security.
"""

import json
import re
from datetime import datetime
from typing import Any, Dict, Optional, List

SUPPORTED_TRANSFORMATIONS = [
    "NONE",
    "TRIM",
    "LOWERCASE",
    "UPPERCASE",
    "STRING_TO_NUMBER",
    "NUMBER_TO_STRING",
    "STRING_TO_DATE",
    "DATE_TO_STRING",
    "BOOLEAN_NORMALIZE",
    "DEFAULT_VALUE",
    "VALUE_MAP",
    "CONCAT",
    "SPLIT"
]

class TransformationError(ValueError):
    """Raised when a field transformation fails validation or conversion."""
    pass

class TransformationEngine:
    @staticmethod
    def get_supported_transformations() -> List[str]:
        return list(SUPPORTED_TRANSFORMATIONS)

    @staticmethod
    def validate_transformation_type(trans_type: str) -> str:
        clean = (trans_type or "NONE").strip().upper()
        if clean not in SUPPORTED_TRANSFORMATIONS:
            raise TransformationError(f"Unsupported transformation type '{trans_type}'. Allowed types: {', '.join(SUPPORTED_TRANSFORMATIONS)}")
        return clean

    @staticmethod
    def parse_config(config_json: Optional[str]) -> Dict[str, Any]:
        if not config_json:
            return {}
        if isinstance(config_json, dict):
            return config_json
        try:
            return json.loads(config_json)
        except Exception as err:
            raise TransformationError(f"Invalid JSON configuration format for transformation: {str(err)}")

    @classmethod
    def apply_transformation(
        cls,
        source_value: Any,
        transformation_type: str,
        transformation_config_json: Optional[str] = None,
        default_value: Optional[str] = None,
        record_context: Optional[Dict[str, Any]] = None
    ) -> Any:
        t_type = cls.validate_transformation_type(transformation_type)
        cfg = cls.parse_config(transformation_config_json)

        if t_type == "NONE":
            if source_value is None and default_value is not None:
                return default_value
            return source_value

        if t_type == "DEFAULT_VALUE":
            def_val = cfg.get("default_value", default_value)
            if source_value is None or source_value == "":
                return def_val
            return source_value

        if source_value is None or source_value == "":
            fallback = cfg.get("default_value", default_value)
            if fallback is not None:
                return fallback
            if t_type in ("TRIM", "LOWERCASE", "UPPERCASE", "NUMBER_TO_STRING"):
                return ""
            if t_type in ("STRING_TO_NUMBER", "BOOLEAN_NORMALIZE"):
                return None

        str_val = str(source_value)

        if t_type == "TRIM":
            return str_val.strip()

        if t_type == "LOWERCASE":
            return str_val.strip().lower()

        if t_type == "UPPERCASE":
            return str_val.strip().upper()

        if t_type == "STRING_TO_NUMBER":
            clean_str = re.sub(r"[^\d.-]", "", str_val).strip()
            if not clean_str:
                return cfg.get("default_value", default_value or 0.0)
            try:
                if "." in clean_str:
                    return float(clean_str)
                return int(clean_str)
            except ValueError:
                raise TransformationError(f"Cannot convert string '{str_val}' to numeric value.")

        if t_type == "NUMBER_TO_STRING":
            decimals = cfg.get("decimals")
            if decimals is not None and isinstance(decimals, int):
                try:
                    num_val = float(str_val)
                    return f"{num_val:.{decimals}f}"
                except ValueError:
                    pass
            return str_val

        if t_type == "STRING_TO_DATE":
            date_formats = cfg.get("date_formats", ["%Y-%m-%d", "%d/%m/%Y", "%d-%m-%Y", "%Y/%m/%d", "%Y%m%d"])
            for fmt in date_formats:
                try:
                    dt = datetime.strptime(str_val.strip(), fmt)
                    return dt.strftime("%Y-%m-%d")
                except ValueError:
                    continue
            raise TransformationError(f"Value '{str_val}' does not match any recognized date formats: {date_formats}")

        if t_type == "DATE_TO_STRING":
            target_fmt = cfg.get("date_format", "%Y-%m-%d")
            try:
                dt = datetime.fromisoformat(str_val.replace("Z", "+00:00"))
                return dt.strftime(target_fmt)
            except ValueError:
                pass
            for fmt in ["%Y-%m-%d", "%d/%m/%Y", "%d-%m-%Y", "%Y/%m/%d"]:
                try:
                    dt = datetime.strptime(str_val.strip(), fmt)
                    return dt.strftime(target_fmt)
                except ValueError:
                    continue
            raise TransformationError(f"Cannot format date '{str_val}' using target format '{target_fmt}'.")

        if t_type == "BOOLEAN_NORMALIZE":
            val_lower = str_val.strip().lower()
            if val_lower in ("true", "1", "yes", "y", "t", "active", "enabled"):
                return True
            if val_lower in ("false", "0", "no", "n", "f", "inactive", "disabled"):
                return False
            return bool(source_value)

        if t_type == "VALUE_MAP":
            mapping_dict = cfg.get("mapping", {})
            if not isinstance(mapping_dict, dict):
                raise TransformationError("VALUE_MAP transformation requires a 'mapping' dictionary in configuration.")
            
            if str_val in mapping_dict:
                return mapping_dict[str_val]
            for k, v in mapping_dict.items():
                if str(k).strip().lower() == str_val.strip().lower():
                    return v
            
            fallback = cfg.get("default_value", default_value)
            if fallback is not None:
                return fallback
            raise TransformationError(f"Value '{str_val}' is not present in VALUE_MAP dictionary: {mapping_dict}")

        if t_type == "CONCAT":
            fields = cfg.get("fields", [])
            sep = cfg.get("separator", " ")
            values = []
            if record_context and isinstance(record_context, dict):
                for f in fields:
                    val = record_context.get(f)
                    if val is not None:
                        values.append(str(val))
            else:
                values.append(str_val)
            return sep.join(values)

        if t_type == "SPLIT":
            delimiter = cfg.get("delimiter", ",")
            index = cfg.get("index", 0)
            parts = str_val.split(delimiter)
            if 0 <= index < len(parts):
                return parts[index].strip()
            fallback = cfg.get("default_value", default_value or "")
            return fallback

        return source_value

transformation_engine = TransformationEngine()
