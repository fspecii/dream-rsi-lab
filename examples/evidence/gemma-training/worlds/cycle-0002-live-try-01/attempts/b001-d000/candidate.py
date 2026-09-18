import re

def slugify(title):
    if not title:
        return ""
    title = title.lower()
    title = re.sub(r'[^a-zA-Z0-9\-\s]', '\-', title)
    title = re.sub(r'[-\s]+', '-', title)
    return title.rstrip('-')
