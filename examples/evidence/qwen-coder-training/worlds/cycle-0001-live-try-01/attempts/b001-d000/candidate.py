import unicodedata

def slugify(title):
    if not title:
        return ''

    normalized_title = unicodedata.normalize('NFKD', title).encode('ASCII', 'ignore').decode('ASCII')
    slug = ''.join(char.lower() for char in normalized_title if char.isalnum() or char == ' ')
    slug = '-'.join(slug.split())
    return slug.strip('-')