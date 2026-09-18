import re

def slugify(title):
    if not title:
        return ""
    title = title.lower()
    title = re.sub(r'[^a-zA-Z0-9\-]+', '-', title)
    slug = re.sub(r'-+', '-', title)
    return slug.strip('-')
