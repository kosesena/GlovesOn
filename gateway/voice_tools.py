"""Ephemeral voice-tool capabilities, separate from read-only event scopes."""
import hashlib
import hmac
import re
from copy import deepcopy
from urllib.parse import urlsplit

from . import session_scope

INLINE_AGENT = 'inline-session'
WRITE_TOOLS = {'post_goods_receipt', 'reverse_goods_receipt', 'send_email', 'place_call', 'save_note'}


def correlation(scope: str, secret: str) -> str:
    return 'gloveson-session-' + hmac.new(secret.encode(), scope.encode(), hashlib.sha256).hexdigest()


def normalize_arguments(arguments: dict) -> dict:
    """Join spoken numeric IDs without stripping legitimate alphanumeric codes."""
    result = deepcopy(arguments)
    for name in ('material', 'plant', 'storage_location', 'purchase_order', 'order', 'document'):
        value = result.get(name)
        if isinstance(value, str):
            value = value.strip()
            if re.fullmatch(r'[0-9\s]+', value):
                value = re.sub(r'\s+', '', value)
            result[name] = value
    return result


def capability(scope_token: str, secret: str) -> str:
    return hmac.new(secret.encode(), b'voice-tools-v1\0' + scope_token.encode(), hashlib.sha256).hexdigest()


def authorized(scope_token: str, supplied: str, secret: str) -> bool:
    if session_scope.verify(scope_token, secret) is None or not isinstance(supplied, str):
        return False
    try:
        return hmac.compare_digest(capability(scope_token, secret), supplied)
    except TypeError:
        return False


def routes(template: dict) -> dict:
    result = {}
    for tool in template['tools']:
        http = tool['http']
        if not http['url'].startswith('{{GATEWAY_PUBLIC_URL}}/erp/'):
            raise ValueError('Voice tools must target template ERP routes')
        result[tool['name']] = (http.get('http_method', 'POST'), http['url'].replace('{{GATEWAY_PUBLIC_URL}}', '', 1))
    return result


def inline_config(template: dict, gateway_url: str) -> dict:
    parsed = urlsplit(gateway_url)
    if parsed.scheme != 'https' or not parsed.hostname or parsed.username or parsed.password:
        raise ValueError('A public HTTPS gateway URL is required')
    routes(template)  # Validate the server-controlled route allowlist.
    result = {k: deepcopy(template[k]) for k in ('system_prompt', 'greeting', 'input', 'output', 'tools') if k in template}
    result.setdefault('output', {})['voice'] = template['voice']['voice_id']
    result['output']['type'] = 'audio'
    result['output'].setdefault('format', {'encoding': 'audio/pcm'})
    for tool in result['tools']:
        tool.pop('http', None)
        tool['type'] = 'function'
    return result
