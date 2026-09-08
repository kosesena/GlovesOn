"""Server-only construction of per-session HTTP tool configuration.

Never return this payload to a browser: it contains the existing tool credential.
Activation requires provider lifecycle management and integration verification.
"""
from copy import deepcopy
from urllib.parse import urlsplit


def build(template: dict, gateway_url: str, tool_secret: str, routing_token: str) -> dict:
    parsed = urlsplit(gateway_url)
    if parsed.scheme != 'https' or not parsed.hostname or parsed.username or parsed.password:
        raise ValueError('A public HTTPS gateway URL is required')
    if not tool_secret or not routing_token:
        raise ValueError('Both tool authentication and routing scope are required')
    result = deepcopy(template)
    result['name'] = 'GlovesOn session'
    for tool in result.get('tools', []):
        http = tool.get('http')
        if not http or not http['url'].startswith('{{GATEWAY_PUBLIC_URL}}/erp/'):
            raise ValueError('Only template ERP tools may be scoped')
        http['url'] = http['url'].replace('{{GATEWAY_PUBLIC_URL}}', gateway_url.rstrip('/'), 1)
        http['headers'] = [
            {'name': 'X-Tool-Secret', 'value': tool_secret},
            {'name': 'X-Event-Scope', 'value': routing_token},
        ]
    if not result.get('tools'):
        raise ValueError('No ERP tools configured')
    return result
