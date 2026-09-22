"""
CtrlBooks - Canonical Field Registry & Capabilities Engine
-----------------------------------------------------------------------
Controlled registry of canonical entity fields, data types, aliases, and source/target capabilities.
Prevents unmapped raw fields and ensures cross-system field compatibility for Tally and future connectors.
"""

from typing import Dict, Any, List

FIELD_REQUIREMENT_SUPPORTED = "SUPPORTED"
FIELD_REQUIREMENT_OPTIONAL = "OPTIONAL"
FIELD_REQUIREMENT_REQUIRED = "REQUIRED"
FIELD_REQUIREMENT_NOT_SUPPORTED = "NOT_SUPPORTED"

DATA_TYPES = ["STRING", "NUMBER", "INTEGER", "DATE", "BOOLEAN"]

CANONICAL_FIELD_REGISTRY: Dict[str, Dict[str, Dict[str, Any]]] = {
    "LEDGER": {
        "name": {
            "canonical_name": "name",
            "data_type": "STRING",
            "requirement_level": FIELD_REQUIREMENT_REQUIRED,
            "description": "Primary ledger or account display name",
            "aliases": ["name", "ledger_name", "ledgername", "account_name", "accountname", "customer_name", "party_name"],
            "source_capability": {"TALLY": FIELD_REQUIREMENT_SUPPORTED},
            "target_capability": {"TALLY": FIELD_REQUIREMENT_SUPPORTED}
        },
        "code": {
            "canonical_name": "code",
            "data_type": "STRING",
            "requirement_level": FIELD_REQUIREMENT_OPTIONAL,
            "description": "Unique account code or alias identifier",
            "aliases": ["code", "ledger_code", "account_code", "alias", "ledger_alias"],
            "source_capability": {"TALLY": FIELD_REQUIREMENT_SUPPORTED},
            "target_capability": {"TALLY": FIELD_REQUIREMENT_SUPPORTED}
        },
        "parent": {
            "canonical_name": "parent",
            "data_type": "STRING",
            "requirement_level": FIELD_REQUIREMENT_OPTIONAL,
            "description": "Parent group or account classification category",
            "aliases": ["parent", "parent_group", "group_name", "under", "parent_name", "account_group"],
            "source_capability": {"TALLY": FIELD_REQUIREMENT_SUPPORTED},
            "target_capability": {"TALLY": FIELD_REQUIREMENT_SUPPORTED}
        },
        "opening_balance": {
            "canonical_name": "opening_balance",
            "data_type": "NUMBER",
            "requirement_level": FIELD_REQUIREMENT_OPTIONAL,
            "description": "Opening financial balance amount",
            "aliases": ["opening_balance", "openingbalance", "op_bal", "opening_bal", "opbalance"],
            "source_capability": {"TALLY": FIELD_REQUIREMENT_SUPPORTED},
            "target_capability": {"TALLY": FIELD_REQUIREMENT_SUPPORTED}
        },
        "closing_balance": {
            "canonical_name": "closing_balance",
            "data_type": "NUMBER",
            "requirement_level": FIELD_REQUIREMENT_OPTIONAL,
            "description": "Closing financial balance amount",
            "aliases": ["closing_balance", "closingbalance", "cl_bal", "closing_bal", "clbalance", "balance"],
            "source_capability": {"TALLY": FIELD_REQUIREMENT_SUPPORTED},
            "target_capability": {"TALLY": FIELD_REQUIREMENT_SUPPORTED}
        },
        "address": {
            "canonical_name": "address",
            "data_type": "STRING",
            "requirement_level": FIELD_REQUIREMENT_OPTIONAL,
            "description": "Mailing address lines",
            "aliases": ["address", "mailing_address", "address_line1", "party_address", "location"],
            "source_capability": {"TALLY": FIELD_REQUIREMENT_SUPPORTED},
            "target_capability": {"TALLY": FIELD_REQUIREMENT_SUPPORTED}
        },
        "phone": {
            "canonical_name": "phone",
            "data_type": "STRING",
            "requirement_level": FIELD_REQUIREMENT_OPTIONAL,
            "description": "Contact telephone or mobile number",
            "aliases": ["phone", "mobile", "contact_number", "phone_number", "mobile_no", "telephone"],
            "source_capability": {"TALLY": FIELD_REQUIREMENT_SUPPORTED},
            "target_capability": {"TALLY": FIELD_REQUIREMENT_SUPPORTED}
        },
        "email": {
            "canonical_name": "email",
            "data_type": "STRING",
            "requirement_level": FIELD_REQUIREMENT_OPTIONAL,
            "description": "Contact email address",
            "aliases": ["email", "email_id", "email_address", "party_email"],
            "source_capability": {"TALLY": FIELD_REQUIREMENT_SUPPORTED},
            "target_capability": {"TALLY": FIELD_REQUIREMENT_SUPPORTED}
        },
        "tax_identifier": {
            "canonical_name": "tax_identifier",
            "data_type": "STRING",
            "requirement_level": FIELD_REQUIREMENT_OPTIONAL,
            "description": "GSTIN, PAN, or tax registration identification number",
            "aliases": ["tax_identifier", "gstin", "gst_no", "gstin_number", "pan", "pan_no", "tax_number"],
            "source_capability": {"TALLY": FIELD_REQUIREMENT_SUPPORTED},
            "target_capability": {"TALLY": FIELD_REQUIREMENT_SUPPORTED}
        },
        "is_active": {
            "canonical_name": "is_active",
            "data_type": "BOOLEAN",
            "requirement_level": FIELD_REQUIREMENT_OPTIONAL,
            "description": "Active ledger flag",
            "aliases": ["is_active", "active", "status", "enabled"],
            "source_capability": {"TALLY": FIELD_REQUIREMENT_SUPPORTED},
            "target_capability": {"TALLY": FIELD_REQUIREMENT_SUPPORTED}
        }
    },
    "STOCK_ITEM": {
        "name": {
            "canonical_name": "name",
            "data_type": "STRING",
            "requirement_level": FIELD_REQUIREMENT_REQUIRED,
            "description": "Stock item display title",
            "aliases": ["name", "item_name", "stock_item_name", "product_name", "item"],
            "source_capability": {"TALLY": FIELD_REQUIREMENT_SUPPORTED},
            "target_capability": {"TALLY": FIELD_REQUIREMENT_SUPPORTED}
        },
        "code": {
            "canonical_name": "code",
            "data_type": "STRING",
            "requirement_level": FIELD_REQUIREMENT_OPTIONAL,
            "description": "Stock item SKU or part number code",
            "aliases": ["code", "sku", "item_code", "part_number", "alias"],
            "source_capability": {"TALLY": FIELD_REQUIREMENT_SUPPORTED},
            "target_capability": {"TALLY": FIELD_REQUIREMENT_SUPPORTED}
        },
        "group": {
            "canonical_name": "group",
            "data_type": "STRING",
            "requirement_level": FIELD_REQUIREMENT_OPTIONAL,
            "description": "Item group or family category",
            "aliases": ["group", "stock_group", "item_group", "category_name", "under"],
            "source_capability": {"TALLY": FIELD_REQUIREMENT_SUPPORTED},
            "target_capability": {"TALLY": FIELD_REQUIREMENT_SUPPORTED}
        },
        "unit": {
            "canonical_name": "unit",
            "data_type": "STRING",
            "requirement_level": FIELD_REQUIREMENT_OPTIONAL,
            "description": "Unit of measure (UOM)",
            "aliases": ["unit", "uom", "unit_of_measure", "base_unit", "units"],
            "source_capability": {"TALLY": FIELD_REQUIREMENT_SUPPORTED},
            "target_capability": {"TALLY": FIELD_REQUIREMENT_SUPPORTED}
        },
        "opening_quantity": {
            "canonical_name": "opening_quantity",
            "data_type": "NUMBER",
            "requirement_level": FIELD_REQUIREMENT_OPTIONAL,
            "description": "Opening inventory stock quantity",
            "aliases": ["opening_quantity", "opening_qty", "op_qty", "qty", "quantity"],
            "source_capability": {"TALLY": FIELD_REQUIREMENT_SUPPORTED},
            "target_capability": {"TALLY": FIELD_REQUIREMENT_SUPPORTED}
        },
        "opening_rate": {
            "canonical_name": "opening_rate",
            "data_type": "NUMBER",
            "requirement_level": FIELD_REQUIREMENT_OPTIONAL,
            "description": "Opening unit valuation rate",
            "aliases": ["opening_rate", "op_rate", "unit_rate", "rate", "cost_price"],
            "source_capability": {"TALLY": FIELD_REQUIREMENT_SUPPORTED},
            "target_capability": {"TALLY": FIELD_REQUIREMENT_SUPPORTED}
        },
        "opening_value": {
            "canonical_name": "opening_value",
            "data_type": "NUMBER",
            "requirement_level": FIELD_REQUIREMENT_OPTIONAL,
            "description": "Total opening inventory valuation amount",
            "aliases": ["opening_value", "op_value", "opening_val", "inventory_value", "value"],
            "source_capability": {"TALLY": FIELD_REQUIREMENT_SUPPORTED},
            "target_capability": {"TALLY": FIELD_REQUIREMENT_SUPPORTED}
        },
        "tax_rate": {
            "canonical_name": "tax_rate",
            "data_type": "NUMBER",
            "requirement_level": FIELD_REQUIREMENT_OPTIONAL,
            "description": "Applicable GST/VAT tax percentage rate",
            "aliases": ["tax_rate", "gst_rate", "tax_percent", "vat_rate"],
            "source_capability": {"TALLY": FIELD_REQUIREMENT_SUPPORTED},
            "target_capability": {"TALLY": FIELD_REQUIREMENT_SUPPORTED}
        },
        "hsn_sac_code": {
            "canonical_name": "hsn_sac_code",
            "data_type": "STRING",
            "requirement_level": FIELD_REQUIREMENT_OPTIONAL,
            "description": "HSN/SAC classification code",
            "aliases": ["hsn_sac_code", "hsn_code", "hsn", "sac_code", "hsn_sac"],
            "source_capability": {"TALLY": FIELD_REQUIREMENT_SUPPORTED},
            "target_capability": {"TALLY": FIELD_REQUIREMENT_SUPPORTED}
        }
    },
    "ACCOUNT_GROUP": {
        "name": {
            "canonical_name": "name",
            "data_type": "STRING",
            "requirement_level": FIELD_REQUIREMENT_REQUIRED,
            "description": "Account group name",
            "aliases": ["name", "group_name", "account_group_name"],
            "source_capability": {"TALLY": FIELD_REQUIREMENT_SUPPORTED},
            "target_capability": {"TALLY": FIELD_REQUIREMENT_SUPPORTED}
        },
        "code": {
            "canonical_name": "code",
            "data_type": "STRING",
            "requirement_level": FIELD_REQUIREMENT_OPTIONAL,
            "description": "Account group code/alias",
            "aliases": ["code", "group_code", "alias"],
            "source_capability": {"TALLY": FIELD_REQUIREMENT_SUPPORTED},
            "target_capability": {"TALLY": FIELD_REQUIREMENT_SUPPORTED}
        },
        "parent": {
            "canonical_name": "parent",
            "data_type": "STRING",
            "requirement_level": FIELD_REQUIREMENT_OPTIONAL,
            "description": "Parent account group",
            "aliases": ["parent", "parent_group", "under"],
            "source_capability": {"TALLY": FIELD_REQUIREMENT_SUPPORTED},
            "target_capability": {"TALLY": FIELD_REQUIREMENT_SUPPORTED}
        }
    },
    "VOUCHER_TYPE": {
        "name": {
            "canonical_name": "name",
            "data_type": "STRING",
            "requirement_level": FIELD_REQUIREMENT_REQUIRED,
            "description": "Voucher type name",
            "aliases": ["name", "voucher_type_name", "type_name"],
            "source_capability": {"TALLY": FIELD_REQUIREMENT_SUPPORTED},
            "target_capability": {"TALLY": FIELD_REQUIREMENT_SUPPORTED}
        },
        "parent": {
            "canonical_name": "parent",
            "data_type": "STRING",
            "requirement_level": FIELD_REQUIREMENT_OPTIONAL,
            "description": "Base voucher type class",
            "aliases": ["parent", "type_class", "under"],
            "source_capability": {"TALLY": FIELD_REQUIREMENT_SUPPORTED},
            "target_capability": {"TALLY": FIELD_REQUIREMENT_SUPPORTED}
        },
        "numbering_method": {
            "canonical_name": "numbering_method",
            "data_type": "STRING",
            "requirement_level": FIELD_REQUIREMENT_OPTIONAL,
            "description": "Voucher numbering method (Automatic, Manual, etc.)",
            "aliases": ["numbering_method", "numbering", "method"],
            "source_capability": {"TALLY": FIELD_REQUIREMENT_SUPPORTED},
            "target_capability": {"TALLY": FIELD_REQUIREMENT_SUPPORTED}
        }
    },
    "UNIT": {
        "name": {
            "canonical_name": "name",
            "data_type": "STRING",
            "requirement_level": FIELD_REQUIREMENT_REQUIRED,
            "description": "Unit name or description",
            "aliases": ["name", "unit_name", "symbol"],
            "source_capability": {"TALLY": FIELD_REQUIREMENT_SUPPORTED},
            "target_capability": {"TALLY": FIELD_REQUIREMENT_SUPPORTED}
        },
        "symbol": {
            "canonical_name": "symbol",
            "data_type": "STRING",
            "requirement_level": FIELD_REQUIREMENT_OPTIONAL,
            "description": "Unit symbol code",
            "aliases": ["symbol", "unit_symbol", "code"],
            "source_capability": {"TALLY": FIELD_REQUIREMENT_SUPPORTED},
            "target_capability": {"TALLY": FIELD_REQUIREMENT_SUPPORTED}
        },
        "decimal_places": {
            "canonical_name": "decimal_places",
            "data_type": "INTEGER",
            "requirement_level": FIELD_REQUIREMENT_OPTIONAL,
            "description": "Decimal precision places",
            "aliases": ["decimal_places", "decimals", "precision"],
            "source_capability": {"TALLY": FIELD_REQUIREMENT_SUPPORTED},
            "target_capability": {"TALLY": FIELD_REQUIREMENT_SUPPORTED}
        }
    },
    "GODOWN": {
        "name": {
            "canonical_name": "name",
            "data_type": "STRING",
            "requirement_level": FIELD_REQUIREMENT_REQUIRED,
            "description": "Godown or warehouse location name",
            "aliases": ["name", "godown_name", "warehouse_name", "material_centre"],
            "source_capability": {"TALLY": FIELD_REQUIREMENT_SUPPORTED},
            "target_capability": {"TALLY": FIELD_REQUIREMENT_SUPPORTED}
        },
        "parent": {
            "canonical_name": "parent",
            "data_type": "STRING",
            "requirement_level": FIELD_REQUIREMENT_OPTIONAL,
            "description": "Parent warehouse group",
            "aliases": ["parent", "under", "parent_location"],
            "source_capability": {"TALLY": FIELD_REQUIREMENT_SUPPORTED},
            "target_capability": {"TALLY": FIELD_REQUIREMENT_SUPPORTED}
        },
        "address": {
            "canonical_name": "address",
            "data_type": "STRING",
            "requirement_level": FIELD_REQUIREMENT_OPTIONAL,
            "description": "Warehouse location address",
            "aliases": ["address", "location_address"],
            "source_capability": {"TALLY": FIELD_REQUIREMENT_SUPPORTED},
            "target_capability": {"TALLY": FIELD_REQUIREMENT_SUPPORTED}
        }
    },
    "COST_CENTRE": {
        "name": {
            "canonical_name": "name",
            "data_type": "STRING",
            "requirement_level": FIELD_REQUIREMENT_REQUIRED,
            "description": "Cost centre or department name",
            "aliases": ["name", "cost_centre_name", "department"],
            "source_capability": {"TALLY": FIELD_REQUIREMENT_SUPPORTED},
            "target_capability": {"TALLY": FIELD_REQUIREMENT_SUPPORTED}
        },
        "category": {
            "canonical_name": "category",
            "data_type": "STRING",
            "requirement_level": FIELD_REQUIREMENT_OPTIONAL,
            "description": "Cost category classification",
            "aliases": ["category", "cost_category"],
            "source_capability": {"TALLY": FIELD_REQUIREMENT_SUPPORTED},
            "target_capability": {"TALLY": FIELD_REQUIREMENT_SUPPORTED}
        }
    }
}

class CanonicalRegistry:
    @staticmethod
    def get_supported_entity_types() -> List[str]:
        return list(CANONICAL_FIELD_REGISTRY.keys())

    @staticmethod
    def is_entity_type_supported(canonical_entity_type: str) -> bool:
        return (canonical_entity_type or "").strip().upper() in CANONICAL_FIELD_REGISTRY

    @staticmethod
    def get_canonical_fields(canonical_entity_type: str) -> Dict[str, Dict[str, Any]]:
        c_type = (canonical_entity_type or "").strip().upper()
        if c_type not in CANONICAL_FIELD_REGISTRY:
            raise ValueError(f"Unsupported canonical entity type '{canonical_entity_type}'. Allowed: {', '.join(CANONICAL_FIELD_REGISTRY.keys())}")
        return CANONICAL_FIELD_REGISTRY[c_type]

    @staticmethod
    def get_supported_source_fields(source_type: str, canonical_entity_type: str) -> List[Dict[str, Any]]:
        c_fields = CanonicalRegistry.get_canonical_fields(canonical_entity_type)
        src = (source_type or "").strip().upper()
        results = []
        for field_name, f_def in c_fields.items():
            cap = f_def.get("source_capability", {}).get(src, FIELD_REQUIREMENT_SUPPORTED)
            if cap != FIELD_REQUIREMENT_NOT_SUPPORTED:
                results.append({
                    "field_name": field_name,
                    "data_type": f_def["data_type"],
                    "requirement_level": f_def["requirement_level"],
                    "description": f_def["description"],
                    "aliases": f_def["aliases"]
                })
        return results

    @staticmethod
    def get_supported_target_fields(target_type: str, canonical_entity_type: str) -> List[Dict[str, Any]]:
        c_fields = CanonicalRegistry.get_canonical_fields(canonical_entity_type)
        tgt = (target_type or "").strip().upper()
        results = []
        for field_name, f_def in c_fields.items():
            cap = f_def.get("target_capability", {}).get(tgt, FIELD_REQUIREMENT_SUPPORTED)
            if cap != FIELD_REQUIREMENT_NOT_SUPPORTED:
                results.append({
                    "field_name": field_name,
                    "data_type": f_def["data_type"],
                    "requirement_level": f_def["requirement_level"],
                    "description": f_def["description"],
                    "aliases": f_def["aliases"]
                })
        return results

canonical_registry = CanonicalRegistry()
