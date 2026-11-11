"""Publication figures from the checked icde02-summary-v1 interface.

No optimizer, simulation, or substituted experimental values are run here.
Execute on an authorized remote compute host after summarize_results.py.
"""
import argparse, collections, hashlib, json, math, pathlib
import numpy as np
import matplotlib
matplotlib.use('Agg')
import matplotlib.pyplot as plt
from matplotlib.colors import LinearSegmentedColormap
from matplotlib.lines import Line2D
from matplotlib.patches import Patch

COL = {'I':'#6B7280','U':'#2563EB','H':'#EA580C','PORTFOLIO':'#15803D','FULL':'#7C3AED','LP':'#0891B2'}
FAMILIES = ('class','range','mixed','iid')
FAMILY_LABELS = {'class':'Categories','range':'Ranges','mixed':'Mixed','iid':'IID selections',
                 'local-class':'Local categories','point-heavy':'Point-heavy','identical':'Identical',
                 'sum':'SUM','groupby':'GROUP BY'}
plt.rcParams.update({'font.family':'DejaVu Sans','font.size':8,'axes.labelsize':8,'axes.titlesize':8.5,
                     'xtick.labelsize':7,'ytick.labelsize':7,'legend.fontsize':7,'pdf.fonttype':42,
                     'ps.fonttype':42,'mathtext.fontset':'dejavusans','axes.spines.top':False,
                     'axes.spines.right':False,'axes.linewidth':.6,'grid.linewidth':.45,
                     'lines.linewidth':1.25,'savefig.facecolor':'white','savefig.bbox':None})


def num(value):
    return isinstance(value,(float,int)) and not isinstance(value,bool) and math.isfinite(value)


def clean(ax, grid=True):
    if grid: ax.grid(axis='y',color='#E5E7EB',zorder=0)
    ax.set_axisbelow(True)


def footer(fig, text):
    fig.text(.5,.025,text,ha='center',va='bottom',fontsize=6.2,color='#4B5563',linespacing=1.25)


def values(rows, key):
    return [r[key] for r in rows if num(r.get(key))]


def good(row):
    return row.get('usable') is True and row.get('standalone') is True


def unique(rows, key='condition_id'):
    by = {}
    for r in rows: by.setdefault(r[key],r)
    return list(by.values())


def unavailable(ax, text='Results unavailable'):
    ax.text(.5,.5,text,ha='center',va='center',transform=ax.transAxes,color='#6B7280')
    ax.set_xticks([]);ax.set_yticks([])


class Figures:
    def __init__(self, obj, out):
        self.data=obj;self.out=out;self.manifest=[]
        self.methods=obj.get('case_methods',[]);self.portfolio=obj.get('portfolios',[])
        out.mkdir(parents=True,exist_ok=True)

    def save(self,fig,name,scope,counts=None):
        fig.align_ylabels()
        dimensions=[float(x) for x in fig.get_size_inches()]
        paths=[]
        for suffix in ('pdf','png'):
            p=self.out/(name+'.'+suffix)
            fig.savefig(p,dpi=300,bbox_inches=None,pad_inches=0)
            paths.append({'path':str(p),'sha256':hashlib.sha256(p.read_bytes()).hexdigest()})
        plt.close(fig)
        self.manifest.append({'figure':name,'scope':scope,'files':paths,'dimensions_inches':dimensions,'counts':counts or {}})

    def phase(self):
        rows=self.data.get('phase',[])
        fig,axs=plt.subplots(1,3,figsize=(7.12,2.50),gridspec_kw={'width_ratios':[1,1,1.1]})
        fig.subplots_adjust(left=.085,right=.985,wspace=.58,bottom=.24,top=.85)
        settings=[(n,f) for n in (8,16) for f in (0,1,2)]
        for panel,(field,title,color) in enumerate((('activation_status','(a) General activation',COL['PORTFOLIO']),
                                                  ('uniform_help_predicted','(b) Uniform activation',COL['U']))):
            matrix=np.full((6,9),np.nan);seen=np.zeros((6,9),dtype=int)
            for i,(n,f) in enumerate(settings):
                for j in range(9):
                    bucket=[r for r in rows if r.get('n')==n and r.get('f')==f and num(r.get('theta')) and abs(r['theta']-j/8)<1e-12]
                    if field=='activation_status':
                        known=[r for r in bucket if r.get(field) in ('help','no-help','positive','nonpositive')]
                        help_count=sum(r[field] in ('help','positive') for r in known)
                    else:
                        known=[r for r in bucket if isinstance(r.get(field),bool)]
                        help_count=sum(r[field] for r in known)
                    seen[i,j]=len(known)
                    if len(known)==4:matrix[i,j]=help_count/4
            cmap=LinearSegmentedColormap.from_list('white_to_method',['#F8FAFC',color]);cmap.set_bad('#D1D5DB')
            im=axs[panel].imshow(matrix,cmap=cmap,vmin=0,vmax=1,aspect='auto',origin='upper')
            axs[panel].set_yticks(range(6),[f'{n}, {f}' for n,f in settings])
            if panel==0:axs[panel].set_ylabel('Owners, colluders')
            axs[panel].set_xticks([0,2,4,6,8],['0','.25','.5','.75','1']);axs[panel].set_xlabel('Point-query weight $\\theta$')
            axs[panel].set_title(title,loc='left')
            for i,j in zip(*np.where(seen!=4)):
                axs[panel].text(j,i,f'{seen[i,j]}/4',ha='center',va='center',fontsize=5.5)
            cb=fig.colorbar(im,ax=axs[panel],orientation='horizontal',fraction=.08,pad=.32,ticks=[0,.5,1])
            cb.ax.set_xticklabels(['0/4','2/4','4/4']);cb.set_label('Orders with a strict gain',fontsize=6.5,labelpad=1)
        ax=axs[2];by=collections.defaultdict(dict)
        for r in self.methods:
            if r['suite']=='A' and r['method'] in ('U','H') and good(r):by[r['case_id']][r['method']]=r
        phase={r['case_id']:r for r in rows};count=0;special=0
        for cid,pair in by.items():
            if set(pair)!={'U','H'}:continue
            x=pair['U'].get('error_normalized');y=pair['H'].get('error_normalized')
            if not(num(x) and num(y)):continue
            p=phase.get(cid,{});nonuniform=p.get('activation_status') in ('help','positive') and p.get('uniform_help_predicted') is False
            ax.scatter(x,y,s=14,color=COL['H'] if nonuniform else '#94A3B8',alpha=.65,edgecolors='none',zorder=3)
            count+=1;special+=int(nonuniform)
        if count:
            ax.plot([0,1.04],[0,1.04],color='#475569',linestyle='--',linewidth=.8)
            ax.set_xlim(0,1.04);ax.set_ylim(0,1.04);ax.set_xticks([0,.5,1]);ax.set_yticks([0,.5,1])
            ax.set_xlabel('Uniform loss / $E_0$');ax.set_ylabel('Harmonic loss / $E_0$')
        else: unavailable(ax)
        ax.set_title('(c) Allocation loss',loc='left');clean(ax)
        footer(fig,f'Matched U/H allocations: {count}/216. Orange: general-only activation ({special} cases).')
        self.save(fig,'activation','All 216 declared A cases; each heatmap cell includes four public owner orders. The scatter uses admitted standalone U/H pairs; orange identifies exact general activation when uniform activation is absent.',{'planned_cases':216,'matched_pairs':count,'general_only_pairs':special})

    def local(self):
        fig,axs=plt.subplots(1,2,figsize=(7.12,2.45));fig.subplots_adjust(left=.105,right=.985,wspace=.38,bottom=.29,top=.85)
        tri=[r for r in self.data.get('triangle',[]) if r.get('verified') and r.get('width_targets_met')]
        ax=axs[0]
        if tri:
            tri=sorted(tri,key=lambda r:r['tau']);x=np.array([r['tau'] for r in tri]);lo=np.array([r['normalized_gap_lower'] for r in tri]);hi=np.array([r['normalized_gap_upper'] for r in tri]);mid=(lo+hi)/2
            ax.errorbar(x,mid,yerr=np.vstack((mid-lo,hi-mid)),color=COL['H'],marker='o',markersize=3.5,capsize=3,label='Exact optimal-value brackets')
            ax.axhline(1/32,color='#475569',linestyle='--',linewidth=.9,label='Asymptotic limit $1/32$')
            ax.set_xscale('log',base=2);ax.set_xticks(x,[r['tau_exact'] for r in tri]);ax.set_xlabel('Total edge-variance budget $\\tau$')
            ax.set_ylabel('$(H^*-P^*)/\\tau^3$');ax.legend(loc='upper left',frameon=False)
        else:unavailable(ax)
        ax.set_title('(a) Cubic-order gap',loc='left');clean(ax)
        rows=self.data.get('local_gaps',[]);ax=axs[1]
        palette={'local-class':COL['U'],'range':COL['PORTFOLIO'],'point-heavy':'#7C3AED','identical':'#64748B'}
        admitted=0
        for family,color in palette.items():
            points=[]
            for tau in sorted({r['tau'] for r in rows if r.get('family')==family and num(r.get('tau'))}):
                bucket=[r for r in rows if r.get('family')==family and r.get('tau')==tau and r.get('usable') and num(r.get('candidate_excess_upper_normalized'))]
                if not bucket:continue
                bycondition=collections.defaultdict(list)
                for r in bucket:bycondition[r['condition_id']].append(r)
                lo=[float(np.mean([r['candidate_excess_lower_normalized'] for r in group])) for group in bycondition.values()]
                hi=[float(np.mean([r['candidate_excess_upper_normalized'] for r in group])) for group in bycondition.values()]
                points.append((tau,float(np.mean(lo)),float(np.mean(hi)),min(lo),max(hi)));admitted+=len(bucket)
            if points:
                p=np.array(points);ax.plot(p[:,0],100*(p[:,1]+p[:,2])/2,marker='o',markersize=3,color=color,label=FAMILY_LABELS[family]);ax.fill_between(p[:,0],100*p[:,3],100*p[:,4],color=color,alpha=.12)
        if admitted:
            ax.set_xscale('log',base=2);ax.set_xticks([1/16,1/4,1/2,2],['1/16','1/4','1/2','2']);ax.set_xlabel('Total edge-variance budget $\\tau$')
            ax.set_ylabel('H candidate excess / $E_0$ (%)');ax.legend(frameon=False,ncol=2,loc='upper left',columnspacing=.8)
        else:unavailable(ax)
        conditions=len({r.get('condition_id') for r in rows if r.get('usable')})
        ax.set_title('(b) H candidate excess',loc='left');clean(ax)
        footer(fig,f'Triangle: {len(tri)}/5 certified brackets. Local cases: {admitted}/{len(rows)}; {conditions} distinct conditions.')
        self.save(fig,'local_gap','Triangle uses certified brackets for both global optima; the normalized gap approaches 1/32. The right panel shows the returned H candidate excess over the full optimum, not an H-optimum gap. Duplicate scientific conditions are combined; shaded bands span condition variability and certified bound widths, without a confidence-interval interpretation.',{'triangle_brackets':len(tri),'planned_triangle':5,'local_admitted':admitted,'local_planned':len(rows),'distinct_local_conditions':conditions})

    def scale(self):
        fig,axs=plt.subplots(1,3,figsize=(7.12,2.50),gridspec_kw={'width_ratios':[1,1,1.15]});fig.subplots_adjust(left=.07,right=.985,wspace=.52,bottom=.31,top=.80)
        timing_counts={}
        for ax,suite,title,methods in ((axs[0],'C','(a) Sparse planning',('U','H','LP')),(axs[1],'Cfull','(b) Full comparison',('U','H','FULL'))):
            timing_counts[suite]={}
            for method in methods:
                points=[]
                rows=[r for r in self.methods if r['suite']==suite and r['method']==method]
                for n in sorted({r['n'] for r in rows}):
                    bucket=[r for r in rows if r['n']==n and good(r) and num(r.get('seconds')) and r['seconds']>0]
                    if bucket:
                        v=values(bucket,'seconds');points.append((n,float(np.median(v)),min(v),max(v),len(bucket)))
                    timed=[r for r in rows if r['n']==n and 'timeout' in str(r.get('execution_status','')).lower() and num(r.get('seconds'))]
                    for r in timed:ax.scatter(n,r['seconds'],marker='x',s=22,color=COL[method],linewidths=.8,zorder=4)
                if points:
                    admitted=sum(int(t[4]) for t in points);p=np.array(points);ax.plot(p[:,0],p[:,1],marker='o',markersize=3,color=COL[method],label=f'{method} {admitted}/{len(rows)}');ax.fill_between(p[:,0],p[:,2],p[:,3],color=COL[method],alpha=.10)
                else:admitted=0
                timing_counts[suite][method]={'standalone_timed':admitted,'planned':len(rows),'fallbacks':sum(r.get('fallback') is True for r in rows)}
            ax.set_xscale('log',base=2);ax.set_yscale('log');ax.set_xlabel('Owners');ax.set_ylabel('Planning time (s)');ax.set_title(title,loc='left');clean(ax)
            ticks=[32,128,512,1024] if suite=='C' else [16,32,64,128];ax.set_xticks(ticks,[str(x) for x in ticks]);ax.legend(frameon=False,loc='upper left')
        ax=axs[2];width=.26;x=np.arange(4);bars=[];fallbacks=[]
        for k,method in enumerate(('U','H')):
            for i,family in enumerate(FAMILIES):
                bucket=[r for r in self.methods if r['suite']=='C' and r['n']==1024 and r.get('family')==family and r['method']==method]
                position=x[i]+(k-.5)*width
                if len(bucket)!=1 or bucket[0].get('usable') is not True or not num(bucket[0].get('error_normalized')):continue
                r=bucket[0];loss=r['error_normalized']
                if good(r):ax.bar(position,loss,width,color=COL[method],zorder=3)
                elif method=='U' and r.get('fallback') is True and r.get('independent_returned') is True:
                    if not math.isclose(loss,1,rel_tol=0,abs_tol=1e-12):raise ValueError('Independence fallback loss is inconsistent')
                    ax.bar(position,loss,width,facecolor='#E5E7EB',edgecolor=COL['I'],hatch='///',linewidth=.7,zorder=3)
                    ax.text(position,.52*loss,'I fallback',rotation=90,ha='center',va='center',fontsize=5.4,color='#374151',zorder=4)
                    fallbacks.append(r['case_id'])
                else:continue
                bars.append({'case_id':r['case_id'],'method':method,'fallback':r.get('fallback') is True,'standalone':good(r),'loss_normalized':loss,'recorded_total_seconds':r.get('seconds') if num(r.get('seconds')) else None})
        handles=[Patch(facecolor=COL['U'],label='U'),Patch(facecolor=COL['H'],label='H')]
        if fallbacks:handles.append(Patch(facecolor='#E5E7EB',edgecolor=COL['I'],hatch='///',label='U fallback to I'))
        fig.legend(handles=handles,loc='upper right',bbox_to_anchor=(.99,.995),ncol=len(handles),frameon=False,columnspacing=.7,handletextpad=.35,fontsize=6.4)
        ax.axhline(1,color=COL['I'],linestyle='--',linewidth=.8);ax.set_ylim(0,1.12);ax.set_xticks(x,['Category','Range','Mixed','IID'],rotation=20,ha='right');ax.set_ylabel('Loss / $E_0$');ax.set_title('(c) Loss at 1,024',loc='left');clean(ax)
        footer(fig,f'Timing: medians and full ranges of total time; legends are standalone/planned. At 1,024: {len(bars)}/8 returned losses, {len(fallbacks)} U fallbacks.')
        fallback_scope=('Gray hatched bars are certified returned independence fallbacks of U at loss/E0=1, not solved uniform optima. ' if fallbacks else 'No independence fallback is plotted; displayed U allocations are standalone. ')
        self.save(fig,'scale','C and Cfull are separate host-matched end-to-end timing panels. Medians and full ranges summarize declared runs; crosses denote recorded time limits. Timing reads total elapsed seconds from the accepted summary, including prior and additional time for any accepted continuation. Timing excludes non-standalone fallbacks and retains their counts. The right panel retains all four 1024-owner conditions. '+fallback_scope+'H remains a separate orange method. Blue U bars denote standalone results.',{'timing':timing_counts,'at_1024':bars,'uniform_independence_fallback_case_ids':fallbacks})

    def grouping(self):
        rows=self.data.get('group_plans',[]);fronts=self.data.get('group_frontiers',[])
        fig,axs=plt.subplots(1,3,figsize=(7.12,2.75),gridspec_kw={'width_ratios':[1,1,1.16]});fig.subplots_adjust(left=.065,right=.985,wspace=.56,bottom=.27,top=.73)
        incomplete_present=False;frontiers_drawn=0
        for ax,family,title in ((axs[0],'class','(a) Categories'),(axs[1],'range','(b) Ranges')):
            selected=[r for r in rows if r.get('case_id')==f'D-n128-{family}-s1401' and r.get('placement')=='balanced']
            for partition,method,label,style in (('fixed8','U','Fixed U','--'),('adaptive','U','Adaptive U','-'),('adaptive','H','Adaptive H','-'),('adaptive','PORTFOLIO','Portfolio','-')):
                points=[r for r in selected if r.get('partition')==partition and r.get('candidate_family')==method and r.get('verified') and r.get('complete')]
                points=sorted(points,key=lambda r:r['price'])
                if points:
                    ax.plot([r['max_host_kib'] for r in points],[r['error_normalized'] for r in points],marker='o',markersize=3,color=COL[method],linestyle=style,label=label)
                    incomplete=[r for r in points if not r.get('method_family_complete')]
                    if incomplete:
                        incomplete_present=True;ax.scatter([r['max_host_kib'] for r in incomplete],[r['error_normalized'] for r in incomplete],marker='D',s=25,facecolors='white',edgecolors=COL[method],linewidths=.8,zorder=5)
            frontier=next((r for r in fronts if r.get('case_id')==f'D-n128-{family}-s1401' and r.get('placement')=='balanced' and r.get('complete') and r.get('method_family_complete') and r.get('coordinate_check_passed')),None)
            if frontier and frontier.get('points'):
                points=sorted(frontier['points'],key=lambda r:r['max_host_kib']);ax.step([r['max_host_kib'] for r in points],[r['error_normalized'] for r in points],where='post',color='#64748B',linestyle=':',linewidth=.8,label='Candidate frontier',zorder=1)
                frontiers_drawn+=1
            if not ax.lines:unavailable(ax,'No verified returned plans')
            ax.set_xlabel('Max-host application KiB');ax.set_ylabel('Loss / $E_0$');ax.set_title(title,loc='left');clean(ax)
        legend={}
        for ax in axs[:2]:
            handles,labels=ax.get_legend_handles_labels()
            for handle,label in zip(handles,labels):
                if label!='Candidate frontier':legend.setdefault(label,handle)
        if legend:fig.legend(list(legend.values()),list(legend),loc='upper center',bbox_to_anchor=(.5,.995),ncol=4,frameon=False,columnspacing=1.2,handletextpad=.4)
        ax=axs[2];plot_values=[];matched=[];pair_records=[]
        for family in FAMILIES:
            candidates=[r for r in rows if r.get('family')==family and r.get('n')==128 and not r.get('interleaved') and num(r.get('price')) and abs(r['price']-.1)<1e-12]
            pairs=collections.defaultdict(dict)
            for r in candidates:
                if not(r.get('verified') and r.get('complete')):continue
                if (r.get('partition'),r.get('candidate_family'))==('fixed8','U'):pairs[(r['case_id'],r['placement'])]['base']=r
                if (r.get('partition'),r.get('candidate_family'))==('adaptive','PORTFOLIO'):pairs[(r['case_id'],r['placement'])]['plan']=r
            v=[]
            for key,pair in sorted(pairs.items()):
                if set(pair)!={'base','plan'}:continue
                b,p=pair['base'],pair['plan']
                if not all(num(r.get(k)) for r in (b,p) for k in ('max_host_kib','error_normalized')) or b['max_host_kib']<=0 or b['error_normalized']<=0:continue
                mse=100*(1-p['error_normalized']/b['error_normalized']);host=100*(1-p['max_host_kib']/b['max_host_kib'])
                complete_family=bool(p.get('method_family_complete') and b.get('method_family_complete'))
                v.append((mse,host,complete_family));pair_records.append({'family':family,'case_id':key[0],'placement':key[1],'mse_reduction_percent':mse,'max_host_byte_reduction_percent':host,'candidate_family_complete':complete_family})
            plot_values.append(v);matched.append(len(v))
        for i,v in enumerate(plot_values):
            if v:
                for metric,shift,marker,filled in ((0,-.20,'o',True),(1,.20,'s',False)):
                    for offset,record in zip(np.linspace(-.12,.12,len(v)),v):
                        complete_family=record[2];incomplete_present|=not complete_family
                        ax.scatter(i+shift+offset,record[metric],s=9,marker=marker if complete_family else 'D',facecolors=COL['PORTFOLIO'] if filled and complete_family else 'white',edgecolors=COL['PORTFOLIO'],linewidths=.7,alpha=.75,zorder=3)
                    median=float(np.median([r[metric] for r in v]));ax.plot([i+shift-.14,i+shift+.14],[median,median],color='#14532D',linewidth=1.5,zorder=4)
        metric_handles=[Line2D([],[],linestyle='None',marker='o',markersize=3.5,color=COL['PORTFOLIO'],label='MSE'),Line2D([],[],linestyle='None',marker='s',markersize=3.5,color=COL['PORTFOLIO'],markerfacecolor='white',label='Max-host bytes')]
        fig.legend(handles=metric_handles,loc='upper right',bbox_to_anchor=(.99,.895),ncol=2,frameon=False,columnspacing=.8,handletextpad=.3,fontsize=6.5)
        ax.axhline(0,color='#64748B',linewidth=.8);ax.set_xlim(-.55,3.55);ax.margins(y=.12);ax.set_xticks(range(4),[f'{x}\n({n}/6)' for x,n in zip(['Cat.','Range','Mixed','IID'],matched)]);ax.set_ylabel('Reduction versus fixed U (%)');ax.set_title('(c) Paired plan changes',loc='left');clean(ax)
        coverage=self.data.get('coverage',{}).get('D',{});verified=coverage.get('verified_scalar_plans',sum(r.get('verified') is True for r in rows));planned=coverage.get('planned_scalar_plans',1344);complete=coverage.get('complete_candidate_family_plans',sum(r.get('method_family_complete') is True for r in rows))
        text=f'Plans: {verified}/{planned} verified; {complete}/{planned} use complete candidate families. Positive reduction is improvement.'
        if incomplete_present:text+='\nOpen diamonds mark incomplete candidate families among displayed feasible plans.'
        footer(fig,text)
        self.save(fig,'grouping','Left panels show the predeclared 128-owner seed1401 balanced cases at all four prices. Scalar planning uses error + lambda*(E0/n)*total endpoint KiB; the horizontal coordinate is maximum-host application KiB with fixed collection l0 included once. A dotted resource frontier appears only when its complete candidate set and coordinates pass readback. The right panel pairs adaptive portfolio and fixed8 U for all three declared seed labels and both placements at lambda=.1, using the same six matched pairs for MSE and maximum-host byte reductions. Every admitted pair is shown; short bars mark medians. Negative host-byte reduction means additional communication for the returned error improvement. Category workloads expose this tradeoff, while the signs for range, mixed, and IID remain visible. Seed labels may repeat a deterministic workload; no independent-workload confidence interval is claimed.',{'verified_scalar_plans':verified,'planned_scalar_plans':planned,'complete_candidate_family_plans':complete,'matched_pairs_by_family':dict(zip(FAMILIES,matched)),'planned_pairs_per_family':6,'paired_changes':pair_records,'incomplete_family_marker_present':incomplete_present,'checked_frontiers_drawn':frontiers_drawn})

    def finite(self):
        rows=self.data.get('finite',[]);fig,axs=plt.subplots(1,3,figsize=(7.12,2.85),gridspec_kw={'width_ratios':[1,1,1.13]});fig.subplots_adjust(left=.07,right=.985,wspace=.72,bottom=.32,top=.80)
        families=('sum','range','groupby','mixed')
        highs=[m['ci_high'] for r in rows if r.get('eligible_for_primary') for m in r.get('methods',{}).values() if num(m.get('ci_high'))]
        upper=max(1.05,1.08*max(highs)) if highs else 1.2;dataset_counts={}
        for ax,dataset,title in ((axs[0],'intel','(a) Intel'),(axs[1],'electricity','(b) Electricity')):
            selected={r.get('family'):r for r in rows if r.get('dataset')==dataset};admitted=0
            for mi,method in enumerate(('I','U','H')):
                x=[];y=[];low=[];high=[];ideal=[]
                for fi,family in enumerate(families):
                    r=selected.get(family,{});m=r.get('methods',{}).get(method,{})
                    if not(r.get('eligible_for_primary') and num(m.get('mean')) and num(m.get('ci_low')) and num(m.get('ci_high'))):continue
                    x.append(fi+(mi-1)*.21);y.append(m['mean']);low.append(max(0,m['mean']-m['ci_low']));high.append(max(0,m['ci_high']-m['mean']));ideal.append(m.get('ideal_normalized_error'));admitted+=1
                if x:
                    ax.errorbar(x,y,yerr=[low,high],fmt='o',markersize=3,color=COL[method],capsize=2,elinewidth=.8,label=method,zorder=3)
                    keep=[i for i,v in enumerate(ideal) if num(v)];ax.scatter([x[i] for i in keep],[ideal[i] for i in keep],marker='_',s=55,color=COL[method],linewidths=1.4,zorder=4)
            ax.axhline(1,color='#9CA3AF',linewidth=.6,linestyle=':');counts=[min([selected.get(f,{}).get('methods',{}).get(m,{}).get('batch_n',0) for m in ('I','U','H')]) if selected.get(f,{}).get('eligible_for_primary') else 0 for f in families]
            ax.set_xticks(range(4),[f'{label}\n({n}/16)' for label,n in zip(['SUM','Range','Group','Mixed'],counts)],rotation=20,ha='right');ax.set_ylabel('Weighted MSE / $E_{\\mathrm{ind}}^{(d)}$');ax.set_ylim(0,upper);ax.set_title(title,loc='left');clean(ax)
            observed=sum(r.get('observed_rows',0) for r in selected.values());planned_rows=sum(r.get('planned_rows',0) for r in selected.values())
            dataset_counts[dataset]={'observed_attempt_rows':observed,'planned_attempt_rows':planned_rows,'paired_batches_by_family':dict(zip(families,counts))}
            if not admitted:unavailable(ax)
        ax=axs[2];ordered=[(d,f) for d in ('intel','electricity') for f in families];labels=[]
        pair_counts={};short={'sum':'SUM','range':'rng','groupby':'grp','mixed':'mix'}
        for i,(d,f) in enumerate(ordered):
            r=next((r for r in rows if r.get('dataset')==d and r.get('family')==f),{});pair=r.get('paired_comparisons',{}).get('H-U',{})
            labels.append(('Int ' if d=='intel' else 'El ')+short[f]);pair_counts[d+'_'+f]=pair.get('batch_n',0) if r.get('eligible_for_primary') else 0
            if r.get('eligible_for_primary') and all(num(pair.get(k)) for k in ('mean','ci_low','ci_high')):
                ax.errorbar(100*pair['mean'],i,xerr=[[100*(pair['mean']-pair['ci_low'])],[100*(pair['ci_high']-pair['mean'])]],fmt='o',markersize=3,color=COL['H'],capsize=2,elinewidth=.8)
        ax.axvline(0,color='#64748B',linestyle='--',linewidth=.8);ax.axhline(3.5,color='#E5E7EB',linewidth=.6);ax.set_yticks(range(8),labels,fontsize=6.5);ax.invert_yaxis();ax.set_xlabel('$(H-U)/E_{\\mathrm{ind}}^{(d)}$ (pp)');ax.set_title('(c) Paired H minus U',loc='left');clean(ax,False)
        handles=[Line2D([],[],linestyle='None',marker='o',markersize=3.5,color=COL[m],label=m) for m in ('I','U','H')]
        handles.append(Line2D([],[],linestyle='None',marker='_',markersize=7,color='#475569',label='Ideal loss'))
        fig.legend(handles=handles,loc='upper left',bbox_to_anchor=(.065,.995),ncol=4,frameon=False,columnspacing=1.2,handletextpad=.35)
        observed=sum(r.get('observed_rows',0) for r in rows);planned_rows=sum(r.get('planned_rows',0) for r in rows);primary=sum(r.get('eligible_for_primary') is True for r in rows)
        footer(fig,f'{primary}/8 fully paired workloads; {observed}/{planned_rows} attempt rows. Intervals use 16 matched batch means.\nPanel (c): Int/El = Intel/Electricity; negative favors H and positive favors U.')
        self.save(fig,'finite_utility','All eight planned real-data workloads are shown with unclipped finite weighted MSE. Intel jointly releases availability COUNT and availability-weighted SUM (dimension two); Electricity has dimension one. The independent reference is E_ind^(d)=dS/r; scalar E0=S/r is used in the other figures. Dots and 95% Student-t intervals use matched batch means, with n/16 under each workload; short horizontal marks show ideal Gaussian loss. Forced-abort rows remain in coverage and are excluded from utility means. The right panel retains the signed H-U difference divided by E_ind^(d) for every workload, with Int/El denoting Intel/Electricity, rng/grp/mix denoting range/GROUP BY/mixed, and pp denoting percentage points. A confidence interval crossing zero does not establish a method advantage. Clipped utility remains separately reported in the checked summary. Unavailable primary comparisons retain 0/16 and are not replaced.',{'datasets':dataset_counts,'paired_difference_batches':pair_counts,'primary_workloads':primary,'planned_workloads':8,'observed_attempt_rows':observed,'planned_attempt_rows':planned_rows})


def main():
    parser=argparse.ArgumentParser(description=__doc__);parser.add_argument('--summary',type=pathlib.Path,required=True);parser.add_argument('--out',type=pathlib.Path,required=True);args=parser.parse_args()
    raw=args.summary.read_bytes();obj=json.loads(raw)
    if obj.get('schema')!='icde02-summary-v1':raise ValueError('Unexpected checked summary schema')
    figures=Figures(obj,args.out)
    for name in ('phase','local','scale','grouping','finite'):getattr(figures,name)()
    manifest={'schema':'icde02-publication-figures-v1','summary_sha256':hashlib.sha256(raw).hexdigest(),
              'script_sha256':hashlib.sha256(pathlib.Path(__file__).read_bytes()).hexdigest(),'figures':figures.manifest,
              'physical':'pending actual physical measurements; no substitute image created'}
    (args.out/'figure_manifest.json').write_text(json.dumps(manifest,sort_keys=True,indent=2),encoding='utf-8')
    print(json.dumps({'figures':len(figures.manifest),'out':str(args.out)}),flush=True)


if __name__=='__main__':main()
