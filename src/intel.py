"""Intel fixed public sensor-day roster; existing private quality/clipping retained."""
import datetime, hashlib, json, pathlib
import numpy as np
from src.vector import availability_value, availability_value_diameter

FIRST_DAY='2004-02-28'
LAST_DAY='2004-04-05'
SENSOR_IDS=tuple(range(1,55))
CLIP_INTERVAL=(0.,1.)

def public_roster():
    first=datetime.date.fromisoformat(FIRST_DAY)
    last=datetime.date.fromisoformat(LAST_DAY)
    return dict(sensor_ids=list(SENSOR_IDS),
        days=[(first+datetime.timedelta(days=j)).isoformat() for j in range((last-first).days+1)],
        source='frozen declared mote IDs 1..54 and documented release calendar 2004-02-28..2004-04-05; constants independent of readings/quality',
        membership='every sensor on every declared day, including all unavailable days')

def dataset():
    roster=public_roster();path=pathlib.Path('data/processed/intel_daily.json')
    rows=json.loads(path.read_text());byday={r['date']:r for r in rows}
    if len(byday)!=len(rows):raise ValueError('duplicate source day')
    if set(byday)-set(roster['days']):raise ValueError('source day outside frozen roster')
    V=np.full((len(roster['days']),54),np.nan)
    for j,day in enumerate(roster['days']):
        if day in byday:
            if len(byday[day]['values'])!=54:raise ValueError('invalid sensor axis')
            V[j]=np.asarray(byday[day]['values'],float)
    S=availability_value(V,*CLIP_INTERVAL)
    # Existing per-owner daily statistic remains the adjacency unit. This
    # does not assert raw-record adjacency or hide quality-dependent absence.
    start=int(len(S)*.7)
    meta=dict(public_roster=roster,clip_interval=list(CLIP_INTERVAL),split_start=start,
        evaluation_days=roster['days'][start:],total_evaluation_days=len(S)-start,
        raw_declared_motes=54,encoded_coordinates=['availability','availability_times_clipped_value'],
        missing='private (0,0); all roster entries participate and communicate',
        input_units='availability count and normalized temperature sum; sum x100 for degrees C',
        sensitivity=availability_value_diameter(*CLIP_INTERVAL),
        original_processed_sha256=hashlib.sha256(path.read_bytes()).hexdigest(),
        empty_source_days=[d for d in roster['days'] if d not in byday],
        available_entries_by_day=S[:,:,0].sum(axis=1).astype(int).tolist(),
        preprocessing='retain original quality rules/daily clipped mean, encode missing without removing roster entries')
    digest=hashlib.sha256(json.dumps(dict(roster=roster,contributions=S.tolist()),sort_keys=True).encode()).hexdigest()
    return 'intel-fixed-public-roster',S[start:],digest,meta
