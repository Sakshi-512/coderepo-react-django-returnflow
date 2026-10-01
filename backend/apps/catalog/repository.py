from .models import Product


def find_by_sku(sku):
    return Product.objects(__raw__={"sku": sku}).as_pymongo().first()
