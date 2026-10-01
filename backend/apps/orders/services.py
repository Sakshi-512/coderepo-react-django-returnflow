from . import repository


def list_orders(viewer, customer_email=None):
    if viewer["role"] == "customer":
        return repository.find_by_customer(viewer["_id"])

    if customer_email:
        from apps.auth import repository as auth_repository

        account = auth_repository.find_active_by_email(customer_email.lower())

        return repository.find_by_customer(account["_id"]) if account else []

    return []
