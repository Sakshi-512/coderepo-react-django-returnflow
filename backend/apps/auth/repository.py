from bson import ObjectId

from .models import WorkspaceAccount


def find_active_by_email(email):
    return WorkspaceAccount.objects(__raw__={"email": email, "active": True}).as_pymongo().first()


def find_active_by_id(account_id):
    return WorkspaceAccount.objects(__raw__={"_id": ObjectId(account_id), "active": True}).as_pymongo().first()
