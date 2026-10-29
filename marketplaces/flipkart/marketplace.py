from app.base import Marketplace


class Flipkart(Marketplace):
    name = "flipkart"
    display_name = "Flipkart"
    latency_ms = (200, 900)

    field_map = {
        "id": "productId",
        "title": "name",
        "price": "pricing.sellingPrice",
        "mrp": "pricing.mrp",
        "category": "vertical",
        "brand": "brand",
        "rating": "ratings.average",
        "reviews": "ratings.totalCount",
        "assured": "fAssured",
        "sponsored": "sponsored",
    }

    def envelope(self, items, total, page, page_size):
        return {"products": items, "count": total, "pageNo": page,
                "hasMore": page * page_size < total}


MARKETPLACE = Flipkart
