import os


def normalize_path(path):
    components = path.split('/')
    stack = []
    for component in components:
        if component == '..':
            if stack:
                stack.pop()
        elif component and component != '.':
            stack.append(component)
    result = '/' + '/'.join(stack)
    return result or '/'
