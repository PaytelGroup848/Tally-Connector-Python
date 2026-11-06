import pytest
from shared.cloud.voucher_group_resolver import build_pl_ledger_group_map, resolve_voucher_group


def test_build_pl_ledger_group_map():
    pl_data = {
        "salesAccounts": {
            "groupName": "Sales Accounts",
            "ledgers": [
                {"ledgerName": "Sales"},
                {"ledgerName": "Sales GST"},
                {"ledgerName": "Sales OMS GST"},
                {"ledgerName": "ROUNDED OFF ( S )"}
            ]
        },
        "purchaseAccounts": {
            "groupName": "Purchase Accounts",
            "ledgers": [
                {"ledgerName": "Purchase"},
                {"ledgerName": "Purchase GST"},
                {"ledgerName": "PURCHASE ON OMS"},
                {"ledgerName": "ROUNDED OFF(P)"}
            ]
        },
        "directExpenses": {
            "groupName": "Direct Expenses",
            "ledgers": [
                {"ledgerName": "Packing & Forwarding ( P )"}
            ]
        },
        "indirectExpenses": {
            "groupName": "Indirect Expenses",
            "ledgers": [
                {"ledgerName": "ELECTRICITY EXPENSES (RESIDENCE)"},
                {"ledgerName": "ACCOUNT WRITING CHARGES"},
                {"ledgerName": "Bank Charges"},
                {"ledgerName": "Mobile Expenses"}
            ]
        },
        "indirectIncomes": {
            "groupName": "Indirect Incomes",
            "ledgers": [
                {"ledgerName": "Packing & Forwarding ( S )"},
                {"ledgerName": "DISCOUNT RECEIVED"}
            ]
        }
    }

    mapping = build_pl_ledger_group_map(pl_data=pl_data)

    assert mapping["sales"] == "Sales Accounts"
    assert mapping["sales gst"] == "Sales Accounts"
    assert mapping["rounded off ( s )"] == "Sales Accounts"
    assert mapping["purchase gst"] == "Purchase Accounts"
    assert mapping["packing & forwarding ( p )"] == "Direct Expenses"
    assert mapping["electricity expenses (residence)"] == "Indirect Expenses"
    assert mapping["bank charges"] == "Indirect Expenses"
    assert mapping["packing & forwarding ( s )"] == "Indirect Incomes"


def test_resolve_sales_quotation_voucher():
    # Scenario: Voucher with type "Sales Quotation" touching ledger "Sales" (From User Image 4)
    pl_ledger_map = {
        "sales": "Sales Accounts",
        "sales gst": "Sales Accounts"
    }

    voucher = {
        "voucherNumber": "WEB-TEST-001",
        "voucherType": "Sales Quotation",
        "partyLedger": "GREENA",
        "lines": [
            {"ledgerName": "GREENA", "amount": -120.0},
            {"ledgerName": "Sales", "amount": 120.0}
        ]
    }

    grp = resolve_voucher_group(voucher, pl_ledger_map=pl_ledger_map)
    assert grp == "Sales Accounts"


def test_resolve_custom_voucher_type():
    # Scenario: User created custom voucher type "Tax Invoice" or "B2B Invoice"
    pl_ledger_map = {
        "sales gst": "Sales Accounts"
    }

    voucher = {
        "voucherNumber": "INV-1001",
        "voucherType": "Tax Invoice",
        "partyLedger": "3 F INDUSTRIES",
        "lines": [
            {"ledgerName": "3 F INDUSTRIES", "amount": -2500.0},
            {"ledgerName": "Sales GST", "amount": 2118.64},
            {"ledgerName": "Output CGST", "amount": 190.68},
            {"ledgerName": "Output SGST", "amount": 190.68}
        ]
    }

    grp = resolve_voucher_group(voucher, pl_ledger_map=pl_ledger_map)
    assert grp == "Sales Accounts"


def test_resolve_expense_payment_voucher():
    # Scenario: Expense paid using Payment voucher
    pl_ledger_map = {
        "electricity expenses (residence)": "Indirect Expenses",
        "bank charges": "Indirect Expenses"
    }

    voucher = {
        "voucherNumber": "PAY-001",
        "voucherType": "Payment",
        "partyLedger": "HDFC Bank",
        "lines": [
            {"ledgerName": "ELECTRICITY EXPENSES (RESIDENCE)", "amount": 5692.0},
            {"ledgerName": "HDFC Bank", "amount": -5692.0}
        ]
    }

    grp = resolve_voucher_group(voucher, pl_ledger_map=pl_ledger_map)
    assert grp == "Indirect Expenses"


def test_resolve_purchase_material_voucher():
    # Scenario: Custom purchase voucher type
    pl_ledger_map = {
        "purchase on oms": "Purchase Accounts"
    }

    voucher = {
        "voucherNumber": "MAT-001",
        "voucherType": "Material Inward",
        "partyLedger": "Supplier XYZ",
        "lines": [
            {"ledgerName": "Supplier XYZ", "amount": 57490.0},
            {"ledgerName": "PURCHASE ON OMS", "amount": -57490.0}
        ]
    }

    grp = resolve_voucher_group(voucher, pl_ledger_map=pl_ledger_map)
    assert grp == "Purchase Accounts"


def test_resolve_contra_fallback():
    # Scenario: Bank transfer (no P&L ledger involved)
    pl_ledger_map = {
        "sales": "Sales Accounts"
    }

    voucher = {
        "voucherNumber": "CONTRA-01",
        "voucherType": "Contra",
        "partyLedger": "Cash",
        "lines": [
            {"ledgerName": "Cash", "amount": -10000.0},
            {"ledgerName": "HDFC Bank", "amount": 10000.0}
        ]
    }

    grp = resolve_voucher_group(voucher, pl_ledger_map=pl_ledger_map)
    assert grp == "Contra"


def test_resolve_receipt_fallback():
    # Scenario: Customer payment received (Balance sheet to Balance sheet)
    pl_ledger_map = {
        "sales": "Sales Accounts"
    }

    voucher = {
        "voucherNumber": "REC-01",
        "voucherType": "Receipt",
        "partyLedger": "Customer ABC",
        "lines": [
            {"ledgerName": "Customer ABC", "amount": -5000.0},
            {"ledgerName": "HDFC Bank", "amount": 5000.0}
        ]
    }

    grp = resolve_voucher_group(voucher, pl_ledger_map=pl_ledger_map)
    assert grp == "Receipt"

