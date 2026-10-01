def collection(model):
    return model._get_collection()


def to_dict(document):
    return dict(document.to_mongo())
