from bson import ObjectId

from .models import Order


def find_by_id(order_id):
    return Order.objects(__raw__={"_id": ObjectId(order_id)}).as_pymongo().first()


def find_by_customer(customer_id):
    return list(Order.objects(__raw__={"customerId": ObjectId(customer_id)}).order_by("-created_at").as_pymongo())


def find_containing_item(order_item_id):
    return Order.objects(__raw__={"items.orderItemId": ObjectId(order_item_id)}).as_pymongo().first()
