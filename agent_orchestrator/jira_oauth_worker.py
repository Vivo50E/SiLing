"""Single explicit login. Suppress all provider output and emit only fixed states."""
import json
import logging
import sys

from .browser_open import open_system_browser
from .jira_oauth import login

ERRORS={'keychain_unavailable','oauth_metadata_invalid','oauth_not_supported','oauth_scope_unsupported',
        'oauth_registration_denied','oauth_token_failed','oauth_denied','oauth_timeout','auth_required'}


def main():
    logging.disable(logging.CRITICAL)
    try:
        body=json.loads(sys.stdin.read(16384))
        def open_browser(url):
            print(json.dumps({'state':'waiting'}),flush=True)
            open_system_browser(url)
        login(body['server_url'],body['account'],open_browser)
        print(json.dumps({'state':'authorized'}),flush=True)
    except BaseException as exc:
        error=str(exc)
        print(json.dumps({'state':'failed','error':error if error in ERRORS else 'oauth_failed'}),flush=True)


if __name__=='__main__':main()
