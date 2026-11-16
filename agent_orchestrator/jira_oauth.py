"""Explicit OAuth code flow and silent refresh for trusted HTTP Jira MCPs."""
from contextlib import contextmanager
import fcntl
import hashlib
from http.server import BaseHTTPRequestHandler, HTTPServer
import json
import os
from pathlib import Path
import re
import secrets
import tempfile
import time
from urllib.parse import parse_qs, urlencode, urlsplit, urlunsplit

import httpx

from .keychain import Keychain, KeychainError


class OAuthError(ValueError):
    pass


def safe_url(value):
    if not isinstance(value,str) or len(value)>4096 or any(ord(c)<33 for c in value):
        raise OAuthError('oauth_metadata_invalid')
    u=urlsplit(value)
    if (not u.hostname or u.username or u.password or u.query or u.fragment
            or '\\' in value or any(x in {'.','..'} for x in u.path.split('/'))
            or (u.scheme!='https' and not (u.scheme=='http' and u.hostname=='127.0.0.1'))):
        raise OAuthError('oauth_metadata_invalid')
    _=u.port
    return value.rstrip('/')


def origin(value):
    u=urlsplit(safe_url(value))
    return u.scheme,u.netloc.lower()


@contextmanager
def credential_lock(account):
    if not re.fullmatch('[a-f0-9]{32}',account):raise OAuthError('auth_required')
    # Per-user private runtime locks only; credentials are exclusively in Keychain.
    root=Path(tempfile.gettempdir())/('siling-jira-oauth-'+str(os.getuid()))
    root.mkdir(mode=0o700,exist_ok=True)
    stat=root.lstat()
    if root.is_symlink() or stat.st_uid!=os.getuid() or stat.st_mode & 0o077:
        raise OAuthError('keychain_unavailable')
    fd=os.open(root/(account+'.lock'),os.O_CREAT|os.O_RDWR|os.O_NOFOLLOW,0o600)
    try:
        started=time.monotonic()
        while True:
            try:fcntl.flock(fd,fcntl.LOCK_EX|fcntl.LOCK_NB);break
            except BlockingIOError:
                if time.monotonic()-started>8:raise OAuthError('oauth_busy')
                time.sleep(.05)
        yield
    finally:os.close(fd)


def json_response(response, error='oauth_metadata_invalid'):
    if response.status_code not in (200,201) or len(response.content)>65536:
        raise OAuthError(error)
    data=response.json()
    if not isinstance(data,dict):raise OAuthError(error)
    return data


def discover(client, server_url):
    server_url=safe_url(server_url)
    response=client.post(server_url,headers={'Accept':'application/json, text/event-stream'},json={
        'jsonrpc':'2.0','id':1,'method':'initialize','params':{'protocolVersion':'2025-03-26',
        'capabilities':{},'clientInfo':{'name':'SiLing','version':'1'}}})
    match=re.search(r'resource_metadata="([^"]+)"',response.headers.get('www-authenticate',''),re.I)
    if response.status_code!=401 or not match:raise OAuthError('oauth_not_supported')
    resource_url=safe_url(match[1])
    if origin(resource_url)!=origin(server_url):raise OAuthError('oauth_metadata_invalid')
    prm=json_response(client.get(resource_url))
    if safe_url(prm.get('resource'))!=server_url:raise OAuthError('oauth_metadata_invalid')
    issuers=prm.get('authorization_servers')
    if not isinstance(issuers,list) or not issuers:raise OAuthError('oauth_metadata_invalid')
    issuer=safe_url(issuers[0]);parts=urlsplit(issuer)
    if urlsplit(server_url).scheme=='https' and parts.scheme!='https':raise OAuthError('oauth_metadata_invalid')
    discovery=urlunsplit((parts.scheme,parts.netloc,'/.well-known/oauth-authorization-server'+parts.path.rstrip('/'),'',''))
    metadata=json_response(client.get(discovery))
    if safe_url(metadata.get('issuer'))!=issuer or 'S256' not in metadata.get('code_challenge_methods_supported',[]):
        raise OAuthError('oauth_metadata_invalid')
    result={'issuer':issuer,'resource':server_url}
    for key in ('authorization_endpoint','token_endpoint','registration_endpoint'):
        endpoint=safe_url(metadata.get(key))
        if origin(endpoint)!=origin(issuer):raise OAuthError('oauth_metadata_invalid')
        result[key]=endpoint
    methods=metadata.get('token_endpoint_auth_methods_supported',[])
    result['auth_method']='client_secret_post' if 'client_secret_post' in methods else 'none' if 'none' in methods else None
    if result['auth_method'] is None:raise OAuthError('oauth_not_supported')
    scopes=prm.get('scopes_supported',[])
    if not isinstance(scopes,list) or len(scopes)>100 or any(not isinstance(s,str) or not re.fullmatch(r'[\x21\x23-\x5b\x5d-\x7e]{1,256}',s) for s in scopes):
        raise OAuthError('oauth_metadata_invalid')
    read=[s for s in scopes if 'read' in s.lower()]
    chosen=read or [s for s in scopes if not re.search('write|delete|admin|manage',s,re.I)]
    if scopes and not chosen:raise OAuthError('oauth_scope_unsupported')
    result['scope']=' '.join(chosen)
    return result


def token_arguments(session, extra):
    args={'client_id':session['client_id'],**extra}
    if session['auth_method']=='client_secret_post':args['client_secret']=session['client_secret']
    return args


def save_tokens(store, session, value):
    if (not isinstance(value.get('access_token'),str) or not value['access_token']
            or value.get('token_type','').lower()!='bearer'
            or any(c in value['access_token'] for c in '\r\n')):
        raise OAuthError('auth_required')
    expires=value.get('expires_in',300)
    if isinstance(expires,bool) or not isinstance(expires,(int,float)) or not 0<expires<=31536000:
        raise OAuthError('auth_required')
    refresh=value.get('refresh_token',session.get('refresh_token'))
    if refresh is not None and (not isinstance(refresh,str) or not refresh or len(refresh)>16384):
        raise OAuthError('auth_required')
    session={**session,'access_token':value['access_token'],'refresh_token':refresh,
             'expires_at':time.time()+expires}
    store.set(session)
    return session


class Callback:
    def __init__(self):
        owner=self
        class Handler(BaseHTTPRequestHandler):
            def log_message(self,*args):pass
            def do_GET(self):
                try:
                    if len(self.path)>16384:raise ValueError()
                    parsed=urlsplit(self.path);query=parse_qs(parsed.query,max_num_fields=16)
                except ValueError:
                    self.send_error(400);return
                valid=(self.headers.get('Host')=='127.0.0.1:'+str(owner.server.server_port)
                       and parsed.path=='/oauth/callback' and len(self.path)<=16384
                       and len(query.get('state',[]))==1
                       and secrets.compare_digest(query['state'][0].encode(),owner.state.encode())
                       and owner.result is None)
                if not valid:self.send_error(400);return
                if len(query.get('code',[]))==1 and not query.get('error'):
                    owner.result=(query['code'][0],None)
                elif len(query.get('error',[]))==1:
                    owner.result=(None,'oauth_denied')
                else:self.send_error(400);return
                text=b'You may close this tab and return to SiLing.'
                self.send_response(200);self.send_header('Content-Type','text/plain; charset=utf-8')
                self.send_header('Cache-Control','no-store');self.send_header('Referrer-Policy','no-referrer')
                self.send_header('Content-Security-Policy',"default-src 'none'; frame-ancestors 'none'")
                self.send_header('Content-Length',str(len(text)));self.end_headers()
                try:self.wfile.write(text)
                except OSError:pass
        self.state=secrets.token_urlsafe(32);self.result=None
        self.server=HTTPServer(('127.0.0.1',0),Handler)
        self.server.timeout=.25
        self.uri='http://127.0.0.1:'+str(self.server.server_port)+'/oauth/callback'

    def wait(self, timeout=240):
        deadline=time.monotonic()+timeout
        while self.result is None:
            if time.monotonic()>deadline:raise OAuthError('oauth_timeout')
            self.server.handle_request()
        if self.result[1]:raise OAuthError(self.result[1])
        return self.result[0]

    def close(self):self.server.server_close()


def login(server_url, account, open_browser, store=None):
    server_url=safe_url(server_url);store=store or Keychain(account)
    # Test writable storage before creating a remote client registration.
    store.set({'pending':True,'server_url':server_url})
    callback=Callback()
    try:
        with httpx.Client(timeout=8,follow_redirects=False) as client:
            metadata=discover(client,server_url)
            registration=json_response(client.post(metadata['registration_endpoint'],json={
                'client_name':'SiLing Dashboard','redirect_uris':[callback.uri],
                'grant_types':['authorization_code','refresh_token'],'response_types':['code'],
                'token_endpoint_auth_method':metadata['auth_method'],'scope':metadata['scope']}),'oauth_registration_denied')
            client_id=registration.get('client_id');secret=registration.get('client_secret')
            if (not isinstance(client_id,str) or not client_id or len(client_id)>8192
                    or registration.get('token_endpoint_auth_method',metadata['auth_method'])!=metadata['auth_method']
                    or (metadata['auth_method']=='client_secret_post' and (not isinstance(secret,str) or not secret))):
                raise OAuthError('oauth_registration_denied')
            session={**metadata,'server_url':server_url,'client_id':client_id,'client_secret':secret}
            verifier=secrets.token_urlsafe(48)
            import base64
            challenge=base64.urlsafe_b64encode(hashlib.sha256(verifier.encode()).digest()).rstrip(b'=').decode()
            url=metadata['authorization_endpoint']+'?'+urlencode({'response_type':'code','client_id':client_id,
                'redirect_uri':callback.uri,'state':callback.state,'code_challenge':challenge,
                'code_challenge_method':'S256','resource':server_url,'scope':metadata['scope']})
            open_browser(url)
            code=callback.wait()
            response=client.post(metadata['token_endpoint'],data=token_arguments(session,{
                'grant_type':'authorization_code','code':code,'code_verifier':verifier,
                'redirect_uri':callback.uri,'resource':server_url}))
            save_tokens(store,session,json_response(response,'oauth_token_failed'))
    finally:callback.close()


class OAuthAuth(httpx.Auth):
    def __init__(self, server_url, account):
        self.server_url=safe_url(server_url);self.account=account

    async def async_auth_flow(self, request):
        with credential_lock(self.account):
            store=Keychain(self.account);session=store.get()
            if not session or session.get('server_url')!=self.server_url or not session.get('access_token'):
                raise OAuthError('auth_required')
            if str(request.url).rstrip('/')!=self.server_url:
                raise OAuthError('auth_required')
            endpoint=safe_url(session.get('token_endpoint'))
            if origin(endpoint)!=origin(session.get('issuer')):raise OAuthError('auth_required')
            refreshed=False
            needs_refresh=session.get('expires_at',0)<=time.time()+30
            for attempt in range(2):
                if needs_refresh:
                    if not session.get('refresh_token'):raise OAuthError('auth_required')
                    response=yield httpx.Request('POST',endpoint,data=token_arguments(session,{
                        'grant_type':'refresh_token','refresh_token':session['refresh_token'],'resource':self.server_url}))
                    await response.aread()
                    session=save_tokens(store,session,json_response(response,'auth_required'))
                    refreshed=True
                request.headers['Authorization']='Bearer '+session['access_token']
                response=yield request
                if response.status_code!=401:return
                await response.aread()
                if refreshed:raise OAuthError('auth_required')
                needs_refresh=True
            raise OAuthError('auth_required')
