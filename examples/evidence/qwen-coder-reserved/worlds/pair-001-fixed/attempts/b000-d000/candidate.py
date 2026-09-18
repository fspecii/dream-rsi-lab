from math import ceil

def paginate(items, page, page_size):
    if page_size <= 0:
        return None
    total = len(items)
    pages = ceil(total / page_size)
    page = max(1, min(page, pages))
    start = (page - 1) * page_size
    end = start + page_size
    return {
        'items': items[start:end],
        'page': page,
        'pages': pages,
        'total': total
    }