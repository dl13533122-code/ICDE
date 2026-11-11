#!/usr/bin/env python3
"""Figure 6 from actual icde02-physical-summary-v1 measurements only.

Outputs a fixed 7.12 x 2.45 inch PDF and a 300-dpi PNG. No physical image is
created when no actual attempt row is available. Run on the remote plotting
host; imports/postprocessing here never start peers, optimizers or simulation.
"""
import argparse
import hashlib
import json
import math
from pathlib import Path as P
import matplotlib
matplotlib.use('Agg')
import matplotlib.pyplot as plt
from matplotlib.lines import Line2D

COL = {'I':'#6B7280','U':'#2563EB','H':'#EA580C','PORTFOLIO':'#15803D'}
plt.rcParams.update({'font.family':'DejaVu Sans','font.size':7.3,'axes.labelsize':7.3,'axes.titlesize':8,
                     'xtick.labelsize':6.7,'ytick.labelsize':6.6,'legend.fontsize':6.5,'pdf.fonttype':42,
                     'ps.fonttype':42,'mathtext.fontset':'dejavusans','axes.spines.top':False,'axes.spines.right':False,
                     'axes.linewidth':.6,'grid.linewidth':.45,'lines.linewidth':1.1,'savefig.facecolor':'white'})


def finite(x): return isinstance(x,(int,float)) and not isinstance(x,bool) and math.isfinite(x)


def unavailable(ax,text):
    ax.text(.5,.5,text,ha='center',va='center',transform=ax.transAxes,color=COL['I'],fontsize=7)


def caption(obj):
    c=obj['coverage']; scopes=c['scopes']; charged='unavailable' if c['charged_attempts'] is None else str(c['charged_attempts'])
    return ('Two-host execution with 128 logical owners. (a) Matched ordinary repetitions compare the maximum-host application '
            'endpoint load of fixed-width U with adaptive portfolio grouping. Each point uses the same successful repetition indices '
            'for both variants; horizontal ranges show their observed repetition ranges. (b) Adaptive/fixed-U online-time ratios at '
            'the same matched indices; circles and whiskers show the median and full range, without a confidence-interval claim. '
            '(c) No-sharing/sharing ratios of maximum-host application bytes, maximum-host TLS-record bytes, and online time '
            'for the predeclared category, balanced, lambda=0.1 fixed-U pair, using the same allocation and routes. '
            'These panels concern application endpoints and TLS records, including within-host endpoints; they do not '
            'measure NIC wire traffic. Application and TLS traffic include one final report collection, whereas online time ends '
            'after the query and excludes that collection. B/S denote balanced/skewed placement; the last label field is lambda. '
            'Numbers beside rows and below ablation categories give admitted ordinary pairs out of 10. Open markers denote an '
            'incomplete repetition set or an incomplete portfolio candidate family; feasible returned portfolio plans are retained. '
            'The sixteen forced aborts and sixteen fresh retries are summarized separately and never enter ordinary timing/traffic '
            f'comparisons. Collected rows: {c["observed_attempts"]}/202 across {c["observed_cases"]}/17 cases; durable charges: {charged}/202. '
            f'Main ordinary validated successes: {scopes["main_ordinary"]["validated_successes"]}/160; no-sharing ordinary successes: '
            f'{scopes["no_sharing_ordinary"]["validated_successes"]}/10; observed forced-abort rows: {scopes["forced_abort"]["observed"]}/16; '
            f'validated retry successes: {scopes["fresh_retry"]["validated_successes"]}/16. '
            f'Exact application-frame model mismatches: {c["model_frame_mismatches"]}/{c["model_frame_checked"]} checked rows. '
            'Unobserved, aborted, failed and readback-invalid attempts remain in the 202-attempt summary and its raw-file references.')


def main():
    parser=argparse.ArgumentParser(description=__doc__);parser.add_argument('--summary',type=P,required=True);parser.add_argument('--out',type=P,required=True)
    args=parser.parse_args();raw=args.summary.read_bytes();obj=json.loads(raw)
    if obj.get('schema')!='icde02-physical-summary-v1':raise ValueError('Unexpected physical summary schema')
    if obj['coverage']['planned_cases']!=17 or obj['coverage']['planned_attempts']!=202 or len(obj['comparisons'])!=8:
        raise ValueError('Physical denominator changed')
    args.out.mkdir(parents=True,exist_ok=True)
    manifest=dict(schema='icde02-physical-figure-v1',summary_sha256=hashlib.sha256(raw).hexdigest(),
                  script_sha256=hashlib.sha256(P(__file__).read_bytes()).hexdigest(),files=[],caption=caption(obj),
                  dimensions_inches=[7.12,2.45],png_dpi=300)
    (args.out/'physical_caption.txt').write_text(manifest['caption']+'\n',encoding='utf-8')
    if obj['coverage']['observed_attempts']==0:
        manifest.update(status='pending',reason='No genuine physical attempt row has been collected; no substitute image generated')
        (args.out/'physical_figure_manifest.json').write_text(json.dumps(manifest,sort_keys=True,indent=2)+'\n',encoding='utf-8')
        print(json.dumps(dict(status='pending',manifest=str(args.out/'physical_figure_manifest.json'))),flush=True);return
    fig,axs=plt.subplots(1,3,figsize=(7.12,2.45),gridspec_kw={'width_ratios':[1.22,1.05,1.05]})
    fig.subplots_adjust(left=.095,right=.985,bottom=.28,top=.80,wspace=.50)
    conditions=obj['comparisons'];labels=[];counts_a=[];counts_b=[];any_a=False;any_b=False
    for i,row in enumerate(conditions):
        labels.append(('Cat.' if row['family']=='class' else 'Range')+' '+('B' if row['placement']=='balanced' else 'S')+' '+('0' if row['lambda_exact']=='0' else '.1'))
        metric=row['metrics']['max_application_kib'];n=metric['ratio']['n'];counts_a.append(n)
        if n:
            b,a=metric['base'],metric['alternative'];open_marker=(n!=10 or row.get('alternative_family_complete') is not True)
            axs[0].plot([b['median'],a['median']],[i,i],color='#CBD5E1',linewidth=.8,zorder=1)
            for values,color,offset in ((b,COL['U'],-.07),(a,COL['PORTFOLIO'],.07)):
                mid=values['median'];axs[0].errorbar(mid,i+offset,xerr=[[max(0,mid-values['minimum'])],[max(0,values['maximum']-mid)]],
                    fmt='o',markersize=3.2,color=color,mfc='white' if open_marker else color,mec=color,capsize=1.7,elinewidth=.7,zorder=3)
            any_a=True
        metric=row['metrics']['online_seconds'];values=metric['ratio'];n=values['n'];counts_b.append(n)
        if n:
            mid=values['median'];open_marker=(n!=10 or row.get('alternative_family_complete') is not True)
            axs[1].errorbar(mid,i,xerr=[[max(0,mid-values['minimum'])],[max(0,values['maximum']-mid)]],fmt='o',markersize=3.5,
                color=COL['PORTFOLIO'],mfc='white' if open_marker else COL['PORTFOLIO'],mec=COL['PORTFOLIO'],capsize=1.8,elinewidth=.75,zorder=3)
            any_b=True
    for ax,counts in zip(axs[:2],(counts_a,counts_b)):
        ax.set_ylim(7.7,-.7);ax.set_yticks(range(8));ax.axhline(3.5,color='#E5E7EB',linewidth=.6)
        ax.grid(axis='x',color='#E5E7EB',zorder=0);ax.set_axisbelow(True);ax.margins(x=.20)
        for i,n in enumerate(counts):ax.text(1.01,i,f'{n}/10',transform=ax.get_yaxis_transform(),fontsize=5.8,va='center',ha='left',color='#4B5563')
    axs[0].set_yticklabels(labels);axs[1].set_yticklabels([])
    axs[0].set_title('(a) Matched host traffic',loc='left');axs[0].set_xlabel('Max-host application KiB')
    axs[1].set_title('(b) Matched online time',loc='left');axs[1].set_xlabel('Adaptive / fixed U');axs[1].axvline(1,color=COL['I'],linestyle='--',linewidth=.7)
    if not any_a:unavailable(axs[0],'No admitted\nordinary pairs')
    if not any_b:unavailable(axs[1],'No admitted\nordinary pairs')
    handles=[Line2D([],[],marker='o',markersize=3.5,linestyle='None',color=COL['U'],label='Fixed U, sharing'),
             Line2D([],[],marker='o',markersize=3.5,linestyle='None',color=COL['PORTFOLIO'],label='Adaptive portfolio, sharing')]
    fig.legend(handles=handles,loc='upper left',bbox_to_anchor=(.07,.995),frameon=False,ncol=2,columnspacing=1.1,handletextpad=.35)
    ax=axs[2];ablation=obj['no_sharing'];seen=False;labels_c=[]
    for i,(metric,label) in enumerate((('max_application_kib','App. bytes'),('max_tls_kib','TLS records'),('online_seconds','Online time'))):
        values=ablation.get('metrics',{}).get(metric,{}).get('ratio',{});n=values.get('n',0);labels_c.append(label+f'\n({n}/10)')
        if n and ablation.get('same_allocation_and_routes'):
            mid=values['median'];ax.errorbar(i,mid,yerr=[[max(0,mid-values['minimum'])],[max(0,values['maximum']-mid)]],fmt='o',markersize=4,
                color=COL['U'],mfc='white' if n!=10 else COL['U'],mec=COL['U'],capsize=2,elinewidth=.8,zorder=3);seen=True
    ax.axhline(1,color=COL['I'],linestyle='--',linewidth=.7);ax.set_xticks(range(3),labels_c,rotation=20,ha='right',fontsize=6.2)
    ax.set_xlim(-.5,2.5);ax.grid(axis='y',color='#E5E7EB');ax.set_axisbelow(True)
    ax.set_ylabel('No-sharing / sharing');ax.set_title('(c) Partial reuse',loc='left')
    if not seen:unavailable(ax,'No admitted\nno-sharing pair')
    c=obj['coverage'];s=c['scopes'];ordinary=s['main_ordinary']['validated_successes']+s['no_sharing_ordinary']['validated_successes']
    charged='?' if c['charged_attempts'] is None else str(c['charged_attempts'])
    footer=(f'Rows {c["observed_attempts"]}/202; cases {c["observed_cases"]}/17; charged {charged}/202; '
            f'ordinary success {ordinary}/170; forced observed {s["forced_abort"]["observed"]}/16; retry success {s["fresh_retry"]["validated_successes"]}/16')
    fig.text(.5,.035,footer,ha='center',va='bottom',fontsize=5.8,color='#374151')
    # No tight bounding box: the physical width/height remain exactly declared.
    for suffix in ('pdf','png'):
        path=args.out/('physical_execution.'+suffix);fig.savefig(path,dpi=300,pad_inches=0)
        manifest['files'].append(dict(path=str(path),sha256=hashlib.sha256(path.read_bytes()).hexdigest()))
    plt.close(fig);manifest.update(status='rendered',coverage=c,planned_panels=3,paired_main_conditions=8,paired_no_sharing_conditions=1)
    (args.out/'physical_figure_manifest.json').write_text(json.dumps(manifest,sort_keys=True,indent=2,allow_nan=False)+'\n',encoding='utf-8')
    print(json.dumps(dict(status='rendered',manifest=str(args.out/'physical_figure_manifest.json'))),flush=True)


if __name__=='__main__':main()
