"""Ephemeral voice-tool capabilities, separate from read-only event scopes."""
from copy import deepcopy
import hashlib
import hmac
from urllib.parse import urlsplit

from . import session_scope

INLINE_AGENT = 'inline-session'


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
