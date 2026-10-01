DEMO_PASSWORD = "password123"
PASSWORD_ROUNDS = 10

ACCOUNT_ROWS = [
    {"name": "Morgan Reyes", "email": "morgan.reyes@returnflow.example", "role": "manager"},
    {"name": "Priya Nair", "email": "priya.nair@returnflow.example", "role": "agent"},
    {"name": "Jordan Blake", "email": "jordan.blake@returnflow.example", "role": "agent"},
    {"name": "Sam Ortiz", "email": "sam.ortiz@returnflow.example", "role": "warehouse"},
    {"name": "Casey Lindqvist", "email": "casey.lindqvist@returnflow.example", "role": "customer"},
    {"name": "Riley Thompson", "email": "riley.thompson@returnflow.example", "role": "customer"},
    {"name": "Drew Kapoor", "email": "drew.kapoor@returnflow.example", "role": "customer"},
]

PRODUCT_ROWS = [
    {"sku": "RF-JCKT-BLK-M", "name": "Weatherproof Jacket, Black, M", "price": "89.00", "variantGroup": "weatherproof-jacket", "returnable": True},
    {"sku": "RF-JCKT-BLK-L", "name": "Weatherproof Jacket, Black, L", "price": "89.00", "variantGroup": "weatherproof-jacket", "returnable": True},
    {"sku": "RF-BOOT-TAN-9", "name": "Trail Boot, Tan, US 9", "price": "129.00", "variantGroup": "trail-boot", "returnable": True},
    {"sku": "RF-BOOT-TAN-10", "name": "Trail Boot, Tan, US 10", "price": "129.00", "variantGroup": "trail-boot", "returnable": True},
    {"sku": "RF-MUG-STEEL", "name": "Insulated Steel Mug", "price": "24.00", "variantGroup": "insulated-mug", "returnable": True},
    {"sku": "RF-GIFT-CARD-50", "name": "Gift Card, $50", "price": "50.00", "variantGroup": "gift-card", "returnable": False},
]

# availableQuantity per SKU. RF-BOOT-TAN-10 is deliberately seeded at 0 so
# the "exchange with insufficient inventory" scenario below is guaranteed,
# not probabilistic.
INVENTORY_ROWS = [
    {"sku": "RF-JCKT-BLK-M", "availableQuantity": 12},
    {"sku": "RF-JCKT-BLK-L", "availableQuantity": 8},
    {"sku": "RF-BOOT-TAN-9", "availableQuantity": 5},
    {"sku": "RF-BOOT-TAN-10", "availableQuantity": 0},
    {"sku": "RF-MUG-STEEL", "availableQuantity": 20},
    {"sku": "RF-GIFT-CARD-50", "availableQuantity": 999},
]

# RETURN_WINDOW_DAYS is not duplicated here -- it's imported directly from
# apps.returns.eligibility in seed.py, so these margins can never silently
# drift out of sync with the real business rule. deliveredDaysAgo values
# below are chosen with wide margin from that boundary (3-10 days = clearly
# in-window, 45 = clearly expired) so the demo's in/out-of-window
# classification is stable across any realistic gap between seed runs.

# Each item carries a stable `scenarioKey` so scripts/seed.py can look up
# exactly which order/item to drive through which real service calls,
# without depending on insertion order or generated ids.
ORDER_ROWS = [
    {
        "customerEmail": "casey.lindqvist@returnflow.example",
        "items": [
            {"scenarioKey": "requested_pending_review", "sku": "RF-JCKT-BLK-M", "quantity": 1, "deliveredDaysAgo": 10},
            {"scenarioKey": "ineligible_rejected", "sku": "RF-MUG-STEEL", "quantity": 2, "deliveredDaysAgo": 45},
            {"scenarioKey": "refund_succeeded", "sku": "RF-BOOT-TAN-9", "quantity": 1, "deliveredDaysAgo": 8},
        ],
    },
    {
        "customerEmail": "riley.thompson@returnflow.example",
        "items": [
            {"scenarioKey": "requested_second", "sku": "RF-JCKT-BLK-M", "quantity": 1, "deliveredDaysAgo": 6},
            {"scenarioKey": "approved_awaiting_item", "sku": "RF-JCKT-BLK-L", "quantity": 1, "deliveredDaysAgo": 6},
            {"scenarioKey": "refund_failed", "sku": "RF-BOOT-TAN-9", "quantity": 1, "deliveredDaysAgo": 6},
        ],
    },
    {
        "customerEmail": "drew.kapoor@returnflow.example",
        "items": [
            {"scenarioKey": "item_received_pending_inspection", "sku": "RF-MUG-STEEL", "quantity": 1, "deliveredDaysAgo": 4},
            {"scenarioKey": "exchange_completed", "sku": "RF-JCKT-BLK-M", "quantity": 1, "deliveredDaysAgo": 4},
            {"scenarioKey": "exchange_awaiting_inventory", "sku": "RF-BOOT-TAN-9", "quantity": 1, "deliveredDaysAgo": 4},
            {"scenarioKey": "rejected_at_inspection", "sku": "RF-JCKT-BLK-L", "quantity": 1, "deliveredDaysAgo": 4},
        ],
    },
]
