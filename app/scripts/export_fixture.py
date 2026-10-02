"""Export the synthetic snapshots/manifest without touching the user's database."""
from pathlib import Path
import json
import sys
import tempfile

ROOT=Path(__file__).resolve().parents[1]
sys.path.insert(0,str(ROOT/'BE'))
from app.config import settings
from app.db import init_db,db_session
from app.pipeline import project_snapshot
from app.sample_data import load_demo

original=settings.database_path
try:
    with tempfile.TemporaryDirectory(prefix='surface-fixture-') as tmp:
        object.__setattr__(settings,'database_path',str(Path(tmp)/'fixture.db'))
        init_db()
        result=load_demo()
        with db_session() as db: snapshot=project_snapshot(db,result['project_id'])
        folder=ROOT/'data/fixtures/acme'
        folder.mkdir(parents=True,exist_ok=True)
        records=[]
        for index,source in enumerate(snapshot['sources'],start=1):
            filename=f'document-{index}.txt'
            (folder/filename).write_text(source['raw_content'],encoding='utf-8',newline='')
            records.append({'document_id':f'acme-{index}','organization':'Acme Robotics (synthetic)',
                            'source_type':source['source_type'],'source_url':source['source_url'],
                            'snapshot_path':filename,'collected_at':source['collected_at'],
                            'sha256':source['content_hash'],'language':'en','split':'development',
                            'content_status':'synthetic_fixture','annotation_status':'code-maintained_fixture',
                            'independent_reviewers':[]})
        manifest={'dataset':'acme-synthetic-v2','purpose':'offline functional regression; not research evaluation',
                  'ground_truth':'../../evaluation_ground_truth.json','documents':records}
        (folder/'manifest.json').write_text(json.dumps(manifest,ensure_ascii=False,indent=2)+'\n',encoding='utf-8')
        print(f'Exported {len(records)} synthetic snapshots to {folder}')
finally:
    object.__setattr__(settings,'database_path',original)
