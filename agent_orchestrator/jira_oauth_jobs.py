"""One bounded explicit browser login; no authorization URLs or tokens in API state."""
import json
from pathlib import Path
import subprocess
import sys
import threading
import time
import uuid

from .jira_mcp import fingerprint, read_json, server_config, connection_scope, InvalidJiraProject
from .jira_oauth import credential_lock
from .keychain import Keychain


def forget(account):
    if not account:return
    with credential_lock(account):Keychain(account).delete()


class JiraOAuthJobs:
    def __init__(self, manager):
        self.manager=manager;self.lock=threading.RLock();self.job=None;self.process=None

    def status(self):
        with self.lock:return dict(self.job or {'state':'idle'})

    def start(self, body):
        if set(body) not in ({'config_file','server_name','base_url'}, {'config_file','server_name','base_url','project_key'}):raise ValueError()
        if sys.platform!='darwin':return {'state':'failed','error':'keychain_unavailable'}
        server=server_config(body['config_file'],body['server_name'])
        if not server.get('url') or server.get('type')=='sse' or server.get('headers'):
            return {'state':'failed','error':'oauth_not_supported'}
        try:
            base,project=connection_scope(body['base_url'] or server.get('env',{}).get('JIRA_URL',''),body.get('project_key',''))
        except InvalidJiraProject:return {'state':'failed','error':'invalid_project'}
        except ValueError:return {'state':'failed','error':'invalid_jira_url'}
        # OAuth endpoints themselves require HTTPS in production (loopback fixtures are supported).
        before=read_json(self.manager.path)
        with self.lock:
            if self.job and self.job['state'] in {'starting','waiting','verifying'}:
                return {**self.job,'error':'oauth_busy'}
            account=uuid.uuid4().hex
            self.job={'id':account,'state':'starting'}
            thread=threading.Thread(target=self.run,args=(dict(body,base_url=base,project_key=project),server,before,account),daemon=True)
            thread.start()
            return dict(self.job)

    def run(self, body, server, before, account):
        committed=False
        try:
            with subprocess.Popen([sys.executable,'-m','agent_orchestrator.jira_oauth_worker'],
                                  stdin=subprocess.PIPE,stdout=subprocess.PIPE,stderr=subprocess.DEVNULL,
                                  text=True,cwd=Path(__file__).resolve().parent.parent) as process:
                with self.lock:
                    if not self.job or self.job.get('id')!=account or self.job['state']=='cancelled':
                        process.kill();process.wait();return
                    self.process=process
                process.stdin.write(json.dumps({'server_url':server['url'],'account':account}));process.stdin.close()
                # A hard deadline also closes the loopback callback if the browser never returns.
                timer=threading.Timer(280,lambda:process.kill() if process.poll() is None else None)
                timer.daemon=True;timer.start()
                try:
                    final=None
                    for line in iter(lambda:process.stdout.readline(1024),''):
                        if len(line)>512:raise ValueError()
                        data=json.loads(line)
                        if data.get('state')=='waiting':
                            with self.lock:
                                if self.job.get('id')==account and self.job['state']!='cancelled':self.job['state']='waiting'
                        elif data.get('state') in {'authorized','failed'}:final=data
                    process.wait(timeout=3)
                finally:
                    timer.cancel()
                    if process.poll() is None:process.kill();process.wait()
                with self.lock:
                    if self.job.get('id')!=account or self.job['state']=='cancelled':return
                    if not final or final['state']!='authorized':
                        self.job={'id':account,'state':'failed','error':(final or {}).get('error','oauth_timeout')};return
                    self.job['state']='verifying'
                if server_config(body['config_file'],body['server_name'])!=server:
                    result={'error':'config_changed'}
                else:
                    result=self.manager.connect(body,_oauth_account=account,_expected=before)
                with self.lock:
                    if result.get('error'):
                        if self.job.get('id')==account and self.job['state']!='cancelled':
                            self.job={'id':account,'state':'failed','error':result['error']}
                    else:
                        committed=True
                        if self.job.get('id')==account:
                            self.job={'id':account,'state':'connected'}
        except BaseException:
            with self.lock:
                if self.job and self.job.get('id')==account and self.job['state']!='cancelled':
                    self.job={'id':account,'state':'failed','error':'oauth_failed'}
        finally:
            with self.lock:
                if self.job and self.job.get('id')==account:self.process=None
            if not committed:
                try:forget(account)
                except (OSError,ValueError):
                    with self.lock:
                        if self.job and self.job.get('id')==account:self.job['error']='keychain_unavailable'

    def cancel(self):
        with self.lock:
            if not self.job or self.job['state'] not in {'starting','waiting','verifying'}:return
            with self.manager.config_lock:
                cfg=read_json(self.manager.path)
                if cfg.get('oauth_account')==self.job['id']:
                    self.job['state']='connected'
                    return
                # Invalidate the compare-and-save of a verification already in flight.
                from .json_store import write_json
                self.manager.path.parent.mkdir(parents=True,exist_ok=True)
                write_json(self.manager.path,{**cfg,'connection_id':uuid.uuid4().hex})
            self.job['state']='cancelled'
            if self.process and self.process.poll() is None:
                self.process.kill()
                self.process.wait(timeout=3)
