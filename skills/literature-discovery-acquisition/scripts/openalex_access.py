#!/usr/bin/env python3
"""OpenAlex environment-key requests and non-secret setup diagnostics (stdlib only)."""
import argparse
import json
import os
import sys
import urllib.error
import urllib.parse
import urllib.request

_warned_keyless = False


def api_key():
    return os.environ.get('OPENALEX_API_KEY', '').strip()


def make_request(url, headers=None):
    """Attach the key only to the HTTPS OpenAlex API; never put it in a URL."""
    global _warned_keyless
    request = urllib.request.Request(url, headers=dict(headers or {}))
    parsed = urllib.parse.urlsplit(url)
    if parsed.scheme != 'https' or parsed.netloc != 'api.openalex.org':
        raise ValueError('OpenAlex credentials require https://api.openalex.org')
    key = api_key()
    if key:
        if any(c.isspace() or ord(c) < 33 or ord(c) > 126 for c in key):
            raise ValueError('OPENALEX_API_KEY has invalid characters; check local configuration')
        # urllib does not copy unredirected headers to a redirected request.
        request.add_unredirected_header('Authorization', 'Bearer ' + key)
    elif not _warned_keyless:
        sys.stderr.write('[OpenAlex] No OPENALEX_API_KEY: anonymous budget is limited. '
                         'Free-key guide: references/openalex_api_key_setup.md\n')
        _warned_keyless = True
    return request


def error_code(exc):
    """Classify errors without echoing response bodies, URLs or credentials."""
    if isinstance(exc, urllib.error.HTTPError):
        try:
            body = exc.read(8192).decode('utf-8', errors='replace').lower()
        except Exception:
            body = ''
        if exc.code == 429:
            if any(s in body for s in ('insufficient budget', 'not_enough_credits', 'insufficient_budget')):
                return 'OPENALEX_BUDGET_EXHAUSTED'
            return 'OPENALEX_RATE_LIMIT_OR_BUDGET'
        if exc.code in (401, 403):
            return 'OPENALEX_KEY_NOT_ACTIVATED' if 'key_not_activated' in body else 'OPENALEX_AUTH_REQUIRED_OR_INVALID'
        return 'OPENALEX_HTTP_%d' % exc.code
    return 'OPENALEX_REQUEST_FAILED'


def check(online=False):
    result = {'key_configured': bool(api_key()), 'key_value': 'NOT_DISPLAYED',
              'guide': 'references/openalex_api_key_setup.md', 'online_validation': 'NOT_RUN'}
    if not online:
        return result, 0
    if not api_key():
        result['online_validation'] = 'KEY_REQUIRED_FOR_RATE_LIMIT_ENDPOINT'
        return result, 2
    try:
        request = make_request('https://api.openalex.org/rate-limit')
        with urllib.request.urlopen(request, timeout=15) as response:
            # Only allowlisted headers are emitted; no raw response or key.
            result['online_validation'] = 'ACCEPTED'
            result['quota_headers'] = {name: response.headers.get(name) for name in (
                'X-RateLimit-Limit', 'X-RateLimit-Remaining', 'X-RateLimit-Reset',
                'X-RateLimit-Limit-USD', 'X-RateLimit-Remaining-USD')}
        return result, 0
    except Exception as exc:
        result['online_validation'] = error_code(exc)
        return result, 1


if __name__ == '__main__':
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--online', action='store_true', help='Validate a configured key with one rate-limit request.')
    args = parser.parse_args()
    payload, status = check(args.online)
    print(json.dumps(payload, ensure_ascii=False, indent=2))
    raise SystemExit(status)
