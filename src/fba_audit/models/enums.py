"""Authoritative Enumerations for the Amazon FBA Audit Engine.

This module provides strongly-typed string enumerations representing all
discrete categories, statuses, reasons, and policy classifications used
throughout ingestion, reconciliation, and claim reporting.
"""

from enum import Enum


class DiscrepancyType(str, Enum):
    """Categorical classification of identified reimbursement discrepancies."""
    # Granular classifications (M1 specification)
    WAREHOUSE_LOST = "WAREHOUSE_LOST"
    WAREHOUSE_DAMAGED = "WAREHOUSE_DAMAGED"
    CUSTOMER_RETURN_NOT_RECEIVED = "CUSTOMER_RETURN_NOT_RECEIVED"
    CARRIER_DAMAGED_RETURN = "CARRIER_DAMAGED_RETURN"
    DIMENSIONAL_WEIGHT_OVERCHARGE = "DIMENSIONAL_WEIGHT_OVERCHARGE"
    SIZE_TIER_OVERCHARGE = "SIZE_TIER_OVERCHARGE"
    INBOUND_RECEIVING_DISCREPANCY = "INBOUND_RECEIVING_DISCREPANCY"

    # Compatibility classifications (Engine reconciler & legacy tests)
    WAREHOUSE_LOST_DAMAGED = "WAREHOUSE_LOST_DAMAGED"
    CUSTOMER_RETURN_NOT_RETURNED = "CUSTOMER_RETURN_NOT_RETURNED"
    DIMENSIONAL_FEE_OVERCHARGE = "DIMENSIONAL_FEE_OVERCHARGE"


class EventType(str, Enum):
    """Event types in SP-API GET_LEDGER_DETAIL_VIEW_DATA."""
    Receipts = "Receipts"
    Shipments = "Shipments"
    CustomerReturns = "CustomerReturns"
    Adjustments = "Adjustments"
    VendorReturns = "VendorReturns"
    WhseTransfers = "WhseTransfers"
    WarehouseTransferInOut = "WarehouseTransferInOut"
    Found = "Found"
    Lost = "Lost"
    Damaged = "Damaged"
    Disposed = "Disposed"
    OtherEvents = "OtherEvents"


class ReasonCode(str, Enum):
    """Authoritative adjustment reason codes and descriptions in inventory ledgers.

    Includes both historical single-letter Amazon codes (M, F, E, D, Q)
    and full text descriptions provided in modern SP-API v2021-06-30 reports.
    """
    # Misplaced / Lost codes
    INVENTORY_MISPLACED = "Inventory misplaced"
    CODE_M = "M"
    CODE_N = "N"
    CODE_P = "P"

    # Found codes
    INVENTORY_FOUND = "Inventory found"
    CODE_F = "F"

    # Warehouse Damaged codes
    DAMAGED_AT_FC = "Damaged at Amazon fulfillment center"
    CODE_E = "E"
    CODE_D = "D"
    CODE_U = "U"

    # Carrier Damaged codes
    DAMAGED_BY_CARRIER = "Damaged by inbound carrier"
    CODE_Q = "Q"

    # Disposal codes
    DISPOSED = "Disposed"
    DESTROYED = "Destroyed"

    # Transfer codes
    TRANSFER = "Transfer"
    CODE_T = "T"

    # Other common codes
    CATALOG_CORRECTION = "Catalog correction"
    CUSTOMER_DAMAGED = "Customer damaged"
    DEFECTIVE = "Defective"


class Disposition(str, Enum):
    """Physical condition disposition of inventory units across reports."""
    SELLABLE = "SELLABLE"
    UNSELLABLE = "UNSELLABLE"
    CUSTOMER_DAMAGED = "CUSTOMER_DAMAGED"
    DEFECTIVE = "DEFECTIVE"
    CARRIER_DAMAGED = "CARRIER_DAMAGED"
    WAREHOUSE_DAMAGED = "WAREHOUSE_DAMAGED"
    DISTRIBUTOR_DAMAGED = "DISTRIBUTOR_DAMAGED"
    DAMAGED = "DAMAGED"
    EXPIRED = "EXPIRED"
    FRAUDULENT_RETURN = "FRAUDULENT_RETURN"


# Alias for backwards compatibility
ReturnDisposition = Disposition


class ReturnStatus(str, Enum):
    """Status of customer returns in GET_FBA_FULFILLMENT_CUSTOMER_RETURNS_DATA."""
    UNIT_RETURNED_TO_INVENTORY = "Unit returned to inventory"
    REIMBURSED = "Reimbursed"
    DISPOSED = "Disposed"
    PENDING = "Pending"
    SCRAPPED = "Scrapped"


class ClaimStatus(str, Enum):
    """Actionable status of an identified discrepancy claim relative to policy windows."""
    ELIGIBLE_NOW = "ELIGIBLE_NOW"                # Open for immediate filing within policy window
    ELIGIBLE = "ELIGIBLE"                        # Compatibility alias
    PENDING_RETURN_WINDOW = "PENDING_RETURN_WINDOW"  # Under 45 days elapsed since customer refund
    PENDING_HOLD = "PENDING_HOLD"                # Compatibility alias
    AUTO_REIMBURSEMENT_PENDING = "AUTO_REIMBURSEMENT_PENDING"  # Days 45-59 awaiting Amazon automation
    REIMBURSED = "REIMBURSED"                    # Already reimbursed
    EXPIRED = "EXPIRED"                          # Beyond policy statute of limitations (e.g. >60/120d)
    DOCUMENTATION_REQUIRED = "DOCUMENTATION_REQUIRED"  # Verified discrepancy needing physical BOL/invoice


class SizeTier(str, Enum):
    """Official Amazon FBA Product Size Tier classifications."""
    SMALL_STANDARD = "Small Standard"
    LARGE_STANDARD = "Large Standard"
    SMALL_OVERSIZE = "Small Oversize"
    MEDIUM_OVERSIZE = "Medium Oversize"
    LARGE_OVERSIZE = "Large Oversize"
    SPECIAL_OVERSIZE = "Special Oversize"


class PolicyCode(str, Enum):
    """Amazon Seller Central Help Hub policy citation codes."""
    POL_FBA_OPS = "POL-FBA-OPS"  # FC Operations Claims Policy (G200213130)
    POL_FBA_RET = "POL-FBA-RET"  # Customer Return Claims Policy (G200213130 / G200379860)
    POL_FBA_INB = "POL-FBA-INB"  # Inbound Shipment Claims Policy (G200453320)
    POL_FBA_DIM = "POL-FBA-DIM"  # Weight and Dimensions Policy (G21213)
    POL_FBA_REM = "POL-FBA-REM"  # Removal Order Claims Policy (G200213130)


class PolicyIdentifier(str, Enum):
    """Legacy Policy Identifiers."""
    WAREHOUSE_OPERATIONS = "G200379860"
    CUSTOMER_RETURNS = "G200213130"
    DIMENSIONAL_WEIGHT = "G21213"
    INBOUND_DEFECTS = "G200453320"
