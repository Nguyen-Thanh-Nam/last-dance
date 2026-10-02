"""Exercise every API route using real curl against a temporary local Uvicorn server."""
from __future__ import annotations

import argparse
import json
import os
import shutil
import socket
import subprocess
import sys
import tempfile
import time
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]


def run(base_url, temporary):
    curl = shutil.which('curl.exe') or shutil.which('curl')
    if not curl:
        raise RuntimeError('curl is required')
    checks, covered = [], set()
    def request(method, path, payload=None, expected=200, quiet=False):
        body = Path(temporary)/'response.body'
        args = [curl, '--silent', '--show-error', '--noproxy', '*', '--connect-timeout', '3', '--max-time', '30',
                '-X', method, '-o', str(body), '-w', '%{http_code}', base_url+path]
        if payload is not None:
            input_path = Path(temporary)/'request.json'
            input_path.write_text(json.dumps(payload,ensure_ascii=False),encoding='utf-8')
            args += ['-H','Content-Type: application/json','--data-binary','@'+str(input_path)]
        completed = subprocess.run(args,capture_output=True,text=True)
        status=int(completed.stdout or '0')
        if completed.returncode or status != expected:
            raise AssertionError(f'{method} {path}: expected {expected}, got {status}; {completed.stderr}; {body.read_text(encoding="utf-8") if body.exists() else ""}')
        content=body.read_text(encoding='utf-8-sig')
        try: data=json.loads(content)
        except json.JSONDecodeError: data=content
        if not quiet:
            checks.append({'method':method,'path':path,'status':status})
            print(f'PASS {method} {path}: {status}',flush=True)
        return data

    request('GET','/api/health')
    request('GET','/')
    spec=request('GET','/openapi.json')
    request('GET','/docs')
    request('GET','/redoc')
    request('GET','/api/projects')
    request('POST','/api/projects/setup',{'domain':'localhost'},expected=422)
    request('POST','/api/projects/setup',{'domain':'example.org','mode':'authorized'},expected=422)
    demo=request('POST','/api/demo/load')
    pid=demo['project_id']
    prefix='/api/projects/'+pid
    detail=request('GET',prefix)
    assets=request('GET',prefix+'/assets')
    request('GET',prefix+'/assets?q=app.acme&asset_type=host&status=related&source=facebook')
    request('GET',prefix+'/assets/'+assets[0]['id'])
    request('PATCH',prefix+'/assets/'+assets[0]['id'],{'classification':'third_party','rationale':'Synthetic classification test','reviewer':'curl-smoke'})
    classified=request('GET',prefix+'/assets/'+assets[0]['id'])
    assert classified['classification']=='third_party' and classified['reviews']
    request('GET',prefix+'/sources/'+detail['sources'][0]['id'])
    request('GET',prefix+'/social')
    relationships=request('GET',prefix+'/relationships')
    graph=request('GET',prefix+'/graph')
    nodes={node['id'] for node in graph['nodes']}
    assert all(edge['source'] in nodes and edge['target'] in nodes for edge in graph['edges'])
    rel=next(r['id'] for r in relationships if r['predicate']=='PRODUCT_USES_WEBSITE')
    claim=request('GET',prefix+'/claims/'+rel)
    request('POST',prefix+'/claims/'+rel+'/evidence',{'source_id':claim['evidence_history'][0]['source_id'],'quote':claim['quote'],'role':'refutes','reviewer':'curl-smoke'})
    for state in ['confirmed','needs_review','rejected']:
        reviewed=request('PATCH',prefix+'/claims/'+rel,{'status':state,'rationale':'curl smoke review','reviewer':'curl-smoke'})
        assert reviewed['status']==state
    job=request('POST',prefix+'/collect',{'collectors':['ai'],'demo':True},expected=202)
    deadline=time.monotonic()+20
    while time.monotonic()<deadline:
        result=request('GET',prefix+'/runs/'+job['run_id'],quiet=True)
        if result['status'] not in {'queued','running'}: break
        time.sleep(.1)
    assert result['status']=='completed'
    request('GET',prefix+'/runs/'+job['run_id'])
    request('GET',prefix+'/runs')
    assert request('GET',prefix+'/claims/'+rel)['status']=='rejected'
    for suffix in ['report.json','report.html','report.csv']:
        request('GET',prefix+'/'+suffix)
    request('POST',prefix+'/collect',{'collectors':['unknown_collector','ai'],'background':False})
    offline=request('POST',prefix+'/collect',{'profile':'full','demo':True,'background':False})
    assert all(c['status']=='skipped' for c in offline['collectors'] if c['collector']!='ai')
    created=request('POST','/api/projects',{'organization_name':'Curl Organization','official_website':'https://example.org',
                    'authorized_scopes':[{'kind':'hostname','value':'example.org','allowed_tests':['http','tls']}]})
    request('GET','/api/projects/'+created['id'])
    edited=request('PUT','/api/projects/'+created['id'],{'organization_name':'Edited Curl Organization','official_website':'https://example.org','aliases':['Curl']})
    assert edited['organization_name']=='Edited Curl Organization'
    # Only test local private-target rejection; no external scan is performed.
    private=request('POST','/api/projects',{'organization_name':'Local Scope Test','official_website':'https://127.0.0.1',
                    'allowed_domains':['127.0.0.1'],'authorized_assets':['127.0.0.1'],'mode':'authorized'})
    blocked=request('POST','/api/projects/'+private['id']+'/collect',{'collectors':['authorized_http','tls'],'background':False})
    assert blocked['status']=='completed_with_errors'
    assert all(c['status']=='error' for c in blocked['collectors'])
    request('POST','/api/projects',{'organization_name':'  ','official_website':'ftp://example.org'},expected=422)
    request('POST','/api/projects',{'organization_name':'Scope mismatch','official_website':'https://other.example','allowed_domains':['example.org']},expected=400)
    request('PATCH',prefix+'/claims/'+rel,{'status':'unknown'},expected=422)
    for suffix in ['', '/assets','/social','/relationships','/graph','/runs','/report.json','/report.html','/report.csv','/claims/missing','/assets/missing','/sources/missing','/runs/missing']:
        request('GET','/api/projects/missing'+suffix,expected=404)
    request('POST','/api/projects/missing/collect',{},expected=404)
    request('PATCH',prefix+'/claims/missing',{'status':'rejected'},expected=404)
    request('DELETE','/api/projects/missing',expected=404)
    for ident in [created['id'],private['id'],pid]:
        request('DELETE','/api/projects/'+ident)
        request('GET','/api/projects/'+ident,expected=404)
    import re
    for path, operations in spec['paths'].items():
        regex='^'+re.sub(r'\{[^}]+\}',r'[^/?]+',path)+'$'
        for method in operations:
            if method not in {'get','post','patch','delete','put'}: continue
            assert any(c['method']==method.upper() and re.match(regex,c['path'].split('?')[0]) for c in checks), f'Untested route: {method} {path}'
            covered.add(method.upper()+' '+path)
    return {'result':'passed','curl_requests':len(checks),'covered_routes':sorted(covered),'api_route_count':sum('/api/' in route for route in covered),
            'checks':checks,'network_scope':'Local server and private-target rejection only. External collectors are tested with fixtures.'}


def main():
    parser=argparse.ArgumentParser()
    parser.add_argument('--output',type=Path,default=ROOT/'docs/verification/curl-results.json')
    args=parser.parse_args()
    with tempfile.TemporaryDirectory(prefix='surface-curl-') as temporary:
        with socket.socket() as probe:
            probe.bind(('127.0.0.1',0))
            port=probe.getsockname()[1]
        env={**os.environ,'DATABASE_PATH':str(Path(temporary)/'smoke.db'),'AI_PROVIDER':'rules-demo',
             'ENABLE_RDAP':'false','REQUEST_DELAY_SECONDS':'0','PYTHONPATH':str(ROOT/'BE')}
        with (Path(temporary)/'server.log').open('w',encoding='utf-8') as log:
            server=subprocess.Popen([sys.executable,'-m','uvicorn','app.main:app','--app-dir',str(ROOT/'BE'),
                                     '--host','127.0.0.1','--port',str(port)],cwd=ROOT,env=env,stdout=log,stderr=log,
                                     creationflags=getattr(subprocess,'CREATE_NO_WINDOW',0))
            try:
                deadline=time.monotonic()+15
                while time.monotonic()<deadline:
                    if server.poll() is not None: raise RuntimeError('Server exited; '+(Path(temporary)/'server.log').read_text())
                    try:
                        with socket.create_connection(('127.0.0.1',port),timeout=.2): break
                    except OSError: time.sleep(.1)
                output=run(f'http://127.0.0.1:{port}',temporary)
                args.output.parent.mkdir(parents=True,exist_ok=True)
                args.output.write_text(json.dumps(output,ensure_ascii=False,indent=2)+'\n',encoding='utf-8')
                print(f"PASS: {output['curl_requests']} curl checks; {output['api_route_count']} API routes. Report: {args.output}")
            finally:
                server.terminate()
                try: server.wait(timeout=10)
                except subprocess.TimeoutExpired: server.kill();server.wait()


if __name__=='__main__':
    main()
