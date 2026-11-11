"""Record the already built and inspected working PDF; never compile or review it."""
import hashlib
import json
import re
import shutil
import subprocess
from datetime import datetime, timezone
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
def sha(p):
    return hashlib.sha256(p.read_bytes()).hexdigest()

source = ROOT / 'manuscript/main.pdf'
dest = ROOT / 'main.pdf'
if dest.exists():
    assert sha(dest) == sha(source), 'Existing root PDF differs: preserve it and resolve ownership'
else:
    shutil.copyfile(source, dest)
info = subprocess.check_output(['pdfinfo', str(dest)], text=True)
pages = int(re.search(r'^Pages:\s+(\d+)', info, re.M).group(1))
aux = (ROOT / 'manuscript/main.aux').read_text()
boundary = int(re.search(r'\\newlabel\{bodyend\}\{\{[^}]*\}\{(\d+)\}', aux).group(1))
assert pages == 10 and boundary == 9 and boundary <= 12
log = (ROOT / 'evidence/latex_r5b_final2.log').read_text()
assert 'Output written on' in log
assert not any(x in log for x in ['Overfull', 'undefined references', 'Undefined control sequence'])
renders = [ROOT / f'evidence/rendered_main_r5b_final/page-{i:02d}.png' for i in range(1,pages+1)]
assert all(p.exists() for p in renders)
utc = datetime.now(timezone.utc).isoformat()
identity = {
    'utc': utc, 'path': str(dest), 'manuscript_path': str(source),
    'sha256': sha(dest), 'bytes': dest.stat().st_size,
    'total_pages': pages, 'body_page_boundary': boundary,
    'references_and_actual_AI_acknowledgment_pages': [10],
    'template': 'IEEEtran 1.8b conference, letter, two column',
    'template_sha256': sha(ROOT / 'manuscript/IEEEtran.cls'),
    'appendix': False, 'supplement': False,
    'author_metadata': 'pending owner input; author field empty, no invented identity',
    'main_pdf_ready_for_web_review': True,
    'scientific_acceptance': 'NOT_REVIEWED',
    'web_review_instruction': None,
    'review_input': 'only this exact main.pdf plus public literature; internal notes/logs are not review input',
    'publication_action': 'none',
    'layout_inspection': 'all ten final rendered pages visually inspected locally for clipping, overlap and readability; not scientific web review',
    'page_renders': {str(p.relative_to(ROOT)): sha(p) for p in renders},
    'source_provenance': {str(p): sha(ROOT / p) for p in [
        Path('manuscript/main.tex'), Path('manuscript/WEB_DRAFT_B5.md'),
        Path('theory/WEB_THEORY_ADDENDUM_v2.md'), Path('theory/WEB_FINITE_BRIDGE_B5.md'),
        Path('governance/WEB_EXECUTION_CONTRACT_R5.md'),
        Path('manuscript/evidence_map_r5b.json'), Path('scripts/manuscript_evidence_r5b.py')]},
    'compile_commands': ['pdflatex -interaction=nonstopmode -halt-on-error -output-directory=manuscript manuscript/main.tex (two final passes)'],
    'render_command': 'pdftoppm -png -r 120 manuscript/main.pdf evidence/rendered_main_r5b_final/page',
    'build_logs': ['evidence/latex_r5b_final1.log', 'evidence/latex_r5b_final2.log', 'evidence/render_main_r5b_final.log'],
    'working_draft_limitations': ['scientific novelty and supplied proof candidates await exact-PDF web review',
        'unchanged original Doppio sources do not build a matched comparison',
        'seven predecessor finite cases lack one-time provisioning wall time; explicitly unmeasured',
        'wall-clock/cache/scheduler side channels excluded; TLS/CSPRNG computational assumptions separate',
        'owner PDF-only constraint versus venue artifact expectation unresolved']
}
(ROOT / 'main_pdf_identity.json').write_text(json.dumps(identity,indent=2)+'\n')
(ROOT / 'manuscript/main_pdf_identity_r5b.json').write_text(json.dumps(identity,indent=2)+'\n')
subprocess.run(['pdftotext','-layout',str(dest),str(ROOT/'evidence/main_text_r5b_final.txt')],check=True)
print(json.dumps({k:identity[k] for k in ['path','sha256','bytes','total_pages','body_page_boundary','main_pdf_ready_for_web_review','scientific_acceptance']}))
