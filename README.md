# ReturnFlow

ReturnFlow is a returns and exchange operations platform for online retail teams. Customers submit returns against delivered orders. Agents, warehouse staff, and managers move each return through review, receiving, inspection, and either a refund or an exchange.

The API is the authority for eligibility, status changes, and inventory. The browser waits for the server before it shows the next state.

## Features

- **Customer return submission.** A customer picks one of their delivered order lines, a reason, a quantity, and either a refund or an exchange SKU in the same variant group.
- **Eligibility checks.** A request is accepted only when the line is delivered, the delivery is inside a 30-day return window, the product is returnable, the reason is valid, and the quantity does not exceed what is still returnable. An ineligible request is stored as `REJECTED` with the rule code in its history.
- **Guarded workflow.** Status changes only through explicit actions. Each action allows a fixed set of source statuses.
- **Customer cancellation.** The owning customer can cancel a return while it is still `REQUESTED`.
- **Staff review.** Agents and managers approve or reject a requested return. Rejection requires a reason code.
- **Warehouse receiving and inspection.** Warehouse staff and managers mark an approved return received, then record a pass or fail inspection. A failed inspection rejects the return.
- **Refunds.** A passing inspection on a refund return starts a simulated charge in the same request. There is no background worker. Further attempts are an explicit action, and they are refused until the server-computed retry time.
- **Deterministic refund simulation.** The gateway is a local lookup, not a payment provider. A profile is chosen once with SHA-256, stored on the refund operation, and reused for every later attempt. Profiles are always succeed, fail once then succeed, or always fail. A cycle allows three attempts.
- **Refund failure and recovery.** After three failed attempts the return sits in `REFUND_FAILED`. A manager can open a new cycle. That cycle has its own idempotency key.
- **Exchanges and inventory.** A passing inspection on an exchange reserves stock with an atomic decrement. If stock is short, the return waits in `EXCHANGE_AWAITING_INVENTORY`. An agent or manager can retry the reservation. A completed reservation is not decremented twice.
- **Authorization.** Sign-in issues a JWT. Customers only see their own orders and returns. Approve, reject, receive, inspect, refund retry, and exchange retry are limited to the roles above.
- **History.** Every transition is appended to the return in the same write that changes its status. A separate audit collection is a projection of that history, not the source of truth.
- **Seeded demo data.** `bun run seed` clears the database and rebuilds ten returns by calling the same service functions the API uses.

## Engineering highlights

- **Guarded transitions.** `ReturnRequest` status changes go through one `find_one_and_update`. The filter requires an allowed current status, and the same update appends the history entry. A conflicting transition returns a conflict instead of overwriting the row.
- **One active return per order line.** A partial unique index allows only one non-terminal return for an order line. `REFUND_FAILED` and `EXCHANGE_AWAITING_INVENTORY` stay non-terminal, so a second return cannot be opened while recovery is still possible.
- **Ownership on read.** A customer who asks for someone else's return gets the same not-found response as a missing id.
- **Concurrency-safe reservation.** Inventory decreases only when `availableQuantity` is still at least the reserved quantity, and only if that reservation has not already been applied.
- **Idempotent refund cycles.** Each refund cycle has a unique idempotency key. A concurrent create of the same cycle returns the existing operation. Recording an attempt is guarded so two callers cannot write the same attempt slot.
- **Retry-safe recovery.** Refund and exchange advance functions can be called again after a partial failure. If the return moved and the related record did not, or the reverse, a later call finishes the step that is missing.
- **Validation before workflow.** Request shape is checked in schema modules. Eligibility is a pure function that receives `now` instead of reading the clock itself. Services apply the workflow rules.
- **MongoDB is the store.** Django is the HTTP layer. `DATABASES` is empty. MongoEngine talks to MongoDB directly.
- **Deterministic seed.** Demo refund outcomes use a forced profile passed through the real inspect path. Demo exchange outcomes depend on seeded stock, including one SKU with quantity zero. Organic returns created in the app still use `assign_profile()`.

## Architecture

```text
Browser (React) -> Django REST API -> service layer -> MongoDB
```

The frontend keeps the signed-in account and the current screen in component state. It does not use a router or a state library. Vite proxies `/api` to the API.

Domain records:

| Record | Role |
| --- | --- |
| `WorkspaceAccount` | Named user with one role: customer, agent, warehouse, or manager |
| `Product` | SKU, price, variant group, and whether the item is returnable |
| `Inventory` | Available and reserved quantity for a SKU |
| `Order` | A customer's historical order and its lines |
| `ReturnRequest` | The return, its inspection, and its append-only history |
| `RefundOperation` | One refund cycle: stored profile, attempts, and idempotency key |
| `InventoryReservation` | Exchange reservation for one return cycle |
| `AuditEvent` | Derived activity row projected from return history |

A refund return moves `REQUESTED` → `APPROVED` → `ITEM_RECEIVED` → `INSPECTED` → `REFUND_PROCESSING` → `COMPLETED`, or to `REFUND_FAILED` when the cycle is exhausted. An exchange uses `EXCHANGE_RESERVING` and, when stock is short, `EXCHANGE_AWAITING_INVENTORY`. `REJECTED` and `CANCELLED` end the return.

## Tech stack

- React 19 and Vite 8
- Bun workspaces
- Python 3.12, Django 5.1, and Django REST Framework
- MongoDB with MongoEngine
- PyJWT and bcrypt

There is no separate frontend test runner, linter, or TypeScript config in this repository.

## Running locally

### Prerequisites

- [Bun](https://bun.sh/)
- Python 3.12
- [uv](https://docs.astral.sh/uv/)
- MongoDB listening on `127.0.0.1:27017`

### Install and start

From the repository root:

```bash
bun install
bun start
```

`bun start` runs `setup.sh` first. That script copies missing `.env` files from the examples, checks MongoDB, creates `.venv` with Python 3.12 if needed, installs `backend/requirements.txt`, and reseeds the database. It then starts the API on port `8000` and the frontend on port `3000`.

Open [http://localhost:3000](http://localhost:3000).

The API health check is [http://localhost:8000/api/v1/health](http://localhost:8000/api/v1/health). It reports whether MongoDB answered a ping.

`frontend/.env.example` sets `VITE_API_URL=/api/v1`, which is the Vite proxy path. `backend/.env.example` sets `MONGODB_URI` to `mongodb://localhost:27017/returnflow_db`.

### Other commands

| Command | What it does |
| --- | --- |
| `bun run seed` | Clears ReturnFlow collections and rebuilds the demo baseline |
| `bun run dev:backend` | Starts only the API on port `8000` |
| `bun run dev:frontend` | Starts only Vite on port `3000` |
| `bun run test` | Runs the Django test suite |
| `cd frontend && bun run build` | Builds the frontend to `frontend/dist` |

`bun start` reseeds on every launch. Restarting only the API or Vite does not reset data. Run `bun run seed` when you want the baseline back.

## Demo accounts

Every seeded account uses the password `password123`.

| Role | Email |
| --- | --- |
| Manager | `morgan.reyes@returnflow.example` |
| Agent | `priya.nair@returnflow.example` |
| Agent | `jordan.blake@returnflow.example` |
| Warehouse | `sam.ortiz@returnflow.example` |
| Customer | `casey.lindqvist@returnflow.example` |
| Customer | `riley.thompson@returnflow.example` |
| Customer | `drew.kapoor@returnflow.example` |

The seed creates ten returns:

1. Requested, waiting for review
2. Rejected at submission because the delivery is outside the return window
3. A second requested return
4. Approved, waiting for the item
5. Received, waiting for inspection
6. Refund completed
7. Refund exhausted its three attempts
8. Exchange completed
9. Exchange waiting because the replacement SKU has no stock
10. Rejected at inspection

## Testing

Backend tests live next to the code they cover:

- `backend/apps/returns/` — eligibility, request schema, workflow services, and HTTP behavior
- `backend/apps/refunds/` — profile assignment, attempt recording, and retry cycles
- `backend/apps/inventory/` — reservation decrement, release, and retry
- `backend/apps/audit/` — audit projection
- `backend/apps/shared/` — shared helpers

```bash
bun run test
```

That runs `python manage.py test apps` with the project virtualenv. The test runner points MongoEngine at a separate database named from `MONGODB_URI` with a `_test` suffix, then drops that database when the run finishes. MongoDB must already be reachable. The dev database used by `bun run seed` is not the test database.

The frontend has a production build and no automated test script:

```bash
cd frontend && bun run build
```

## Screenshots

Screenshots are not in the repository yet. Add them here after capturing the running app:

- Sign-in
- Customer return list and submission form
- Return detail, including history
- Staff operations queue
- Warehouse inspection and refund or exchange progress
