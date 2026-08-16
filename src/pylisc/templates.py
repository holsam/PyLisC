'''
PyLisC: filename template parsing for frames mode

A template describes a filename's delimited fields, e.g.:
    '{}_{position}_{}_{tilt}_{}_{}_{}_{}.mrc'
'{}' fields are ignored; named '{name}' fields are captured. Field content stops at
any character in `delimiters` (default '_' only); everything outside braces is
matched literally, so the delimiter characters actually used in the template still
need to appear in `delimiters` to be treated as separators rather than literal text.
'''

# Import external libraries
import re


def compile_template(template: str, delimiters: str = '_') -> re.Pattern:
    field_class = f'[^{re.escape(delimiters)}]+'
    tokens = re.split(r'(\{[^}]*\})', template)
    pattern_parts = []
    for token in tokens:
        if token.startswith('{') and token.endswith('}'):
            name = token[1:-1]
            if not name:
                pattern_parts.append(field_class)
            elif name.isidentifier():
                pattern_parts.append(f'(?P<{name}>{field_class})')
            else:
                raise ValueError(f'invalid template field name: {name!r}')
        else:
            pattern_parts.append(re.escape(token))
    return re.compile('^' + ''.join(pattern_parts) + '$')


def extract_tilt_angle(filename: str, pattern: re.Pattern) -> float:
    match = pattern.match(filename)
    if match is None:
        raise ValueError(f'filename {filename!r} does not match --filename-template')
    fields = match.groupdict()
    if 'tilt' not in fields:
        raise ValueError('--filename-template must include a {tilt} field')
    try:
        return float(fields['tilt'])
    except ValueError as e:
        raise ValueError(f'could not parse tilt angle {fields["tilt"]!r} from {filename!r}') from e
