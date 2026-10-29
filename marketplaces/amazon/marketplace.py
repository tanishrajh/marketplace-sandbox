from app.base import Marketplace, pages


class Amazon(Marketplace):
    name = "amazon"
    display_name = "Amazon India"
    latency_ms = (100, 500)

    # Add a line here to make a new field filterable (left = query param name, right = path in data.json).
    field_map = {
        "id": "asin",
        "title": "title",
        "price": "price",
        "mrp": "list_price",
        "category": "category",
        "brand": "brand",
        "rating": "rating.stars",
        "reviews": "rating.count",
        "sponsored": "sponsored",
    }

    def envelope(self, items, total, page, page_size):
        return {"search_results": items,
                "pagination": {"page": page, "page_size": page_size,
                               "total_results": total, "total_pages": pages(total, page_size)}}

    def detail(self, raw):
        return {"product": raw}


MARKETPLACE = Amazon
