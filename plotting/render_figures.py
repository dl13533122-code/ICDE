#!/usr/bin/env python3
"""Replot the archived experimental panels; no experiments or statistical fits are run."""
from pathlib import Path
import argparse, csv, json, hashlib
import numpy as np
import matplotlib
matplotlib.use('Agg')
import matplotlib.pyplot as plt
from matplotlib.colors import LinearSegmentedColormap
from matplotlib.lines import Line2D
from matplotlib.patches import Rectangle
from matplotlib.ticker import FixedLocator, NullLocator, FuncFormatter

ROOT=Path(__file__).resolve().parent
C={'H':'#087F8C','U':'#62799C','I':'#9DA5B1','FULL':'#BE774C','LP':'#9787AF',
   'Portfolio':'#174E52','Fixed U':'#95A1B4','Adaptive U':'#62799C','Adaptive H':'#087F8C',
   'ink':'#29343E','muted':'#6D7782','grid':'#E6EAED','accent':'#B86F36'}
FAM={'local-class':('#087F8C','o','Categories'),'range':('#62799C','s','Ranges'),
     'point-heavy':('#B5834B','^','Point-heavy'),'identical':('#9683A6','D','Identical')}
W=7.14; CW=3.486
plt.rcParams.update({'font.family':'DejaVu Sans','font.size':8.0,'axes.labelsize':8.0,
 'xtick.labelsize':7.1,'ytick.labelsize':7.1,'axes.titlesize':8.4,'axes.titleweight':'bold',
 'axes.labelcolor':C['ink'],'text.color':C['ink'],'xtick.color':C['muted'],'ytick.color':C['muted'],
 'axes.edgecolor':'#A3ABB3','axes.linewidth':.55,'lines.linewidth':1.15,
 'xtick.major.width':.5,'ytick.major.width':.5,'xtick.major.size':2.4,'ytick.major.size':2.4,
 'xtick.major.pad':2.5,'ytick.major.pad':2.5,'legend.fontsize':7.2,'legend.frameon':False,
 'legend.handlelength':1.45,'legend.handletextpad':.45,'legend.columnspacing':1.1,
 'mathtext.fontset':'stix','pdf.fonttype':42,'ps.fonttype':42,'svg.fonttype':'none',
 'figure.facecolor':'white','axes.facecolor':'white','savefig.facecolor':'white'})
AUDIT={'panels':{},'annotations':{},'artist_boundary_warnings':[],'data_range_checks':[]}

def rows(folder, name):
 p=ROOT/'data'/folder/name
 a=list(csv.DictReader(p.open()))
 AUDIT['panels'][folder+'/'+name]={'rows':len(a),'sha256':hashlib.sha256(p.read_bytes()).hexdigest()}
 return a

def f(r,k):return float(r[k])
def arr(a,k):return np.asarray([f(r,k) for r in a])
def axes(fig, box):
 w,h=fig.get_size_inches();return fig.add_axes([box[0]/w,box[1]/h,box[2]/w,box[3]/h])
def clean(ax, grid='y'):
 ax.spines[['top','right']].set_visible(False)
 ax.set_axisbelow(True)
 if grid:ax.grid(axis=grid,color=C['grid'],linewidth=.45)
 ax.tick_params(which='minor',bottom=False,left=False)
 ax.xaxis.set_minor_locator(NullLocator());ax.yaxis.set_minor_locator(NullLocator())
def title(ax,label,text):
 ax.set_title(f'({label}) {text}',loc='left',pad=7)
def handle(name,color,marker='o',ls='-',open=False):
 return Line2D([],[],label=name,color=color,marker=marker,markersize=3.6,
               markerfacecolor='white' if open else color,markeredgewidth=.85,linestyle=ls,linewidth=1.1)
def save(fig,name,out):
 fig.canvas.draw();renderer=fig.canvas.get_renderer();box=fig.bbox
 for i,ax in enumerate(fig.axes):
  xmin,xmax=sorted(ax.get_xlim());ymin,ymax=sorted(ax.get_ylim())
  dx0,dy0,dx1,dy1=ax.dataLim.extents
  ok=(dx0>=xmin-1e-9 and dx1<=xmax+1e-9 and dy0>=ymin-1e-9 and dy1<=ymax+1e-9)
  AUDIT['data_range_checks'].append({'figure':name,'axis':i,'limits':[xmin,xmax,ymin,ymax],'data_bounds':[dx0,dx1,dy0,dy1],'all_data_and_intervals_visible':bool(ok)})
  assert ok,(name,i,ax.dataLim.extents,ax.get_xlim(),ax.get_ylim())
 for txt in fig.findobj(matplotlib.text.Text):
  if not txt.get_visible() or not txt.get_text():continue
  bb=txt.get_window_extent(renderer)
  if bb.width and (bb.x0<box.x0-1 or bb.x1>box.x1+1 or bb.y0<box.y0-1 or bb.y1>box.y1+1):
   AUDIT['artist_boundary_warnings'].append({'figure':name,'text':txt.get_text(),'bbox':list(bb.bounds)})
 for suffix in ['pdf','svg','png']:
  fig.savefig(out/(name+'.'+suffix),dpi=320,metadata={'Creator':'ICDE02 plotting source'} if suffix=='pdf' else None)
 plt.close(fig)

def activation(out):
 a=rows('fig1_activation','panel_a_heatmap_general_activation.csv')
 b=rows('fig1_activation','panel_b_heatmap_uniform_activation.csv')
 s=rows('fig1_activation','panel_c_scatter_U_vs_H.csv')
 fig=plt.figure(figsize=(W,1.91))
 ax1=axes(fig,[.52,.39,1.70,1.17]);ax2=axes(fig,[2.55,.39,1.79,1.17]);ax3=axes(fig,[4.98,.39,1.95,1.17])
 settings=[(n,c) for n in (8,16) for c in range(3)]
 mats=[]
 for ax,data,col,label,heading in [(ax1,a,C['H'],'a','General activation'),(ax2,b,C['U'],'b','Uniform activation')]:
  z=np.zeros((6,9),int)
  for r in data:z[settings.index((int(r['n_owners']),int(r['f_colluders']))),round(f(r,'theta_value')*8)]=int(r['orders_with_strict_gain'])
  mats.append(z)
  cmap=LinearSegmentedColormap.from_list('counts',['#F4F6F7',col])
  ax.imshow(z,cmap=cmap,vmin=0,vmax=4,aspect='auto',interpolation='nearest')
  for (i,j),v in np.ndenumerate(z):ax.text(j,i,str(v),ha='center',va='center',fontsize=7.3,color='white' if v>=3 else '#67727C')
  ax.set_xticks([0,2,4,6,8],['0','.25','.5','.75','1'])
  ax.set_yticks(range(6),[f'{n}, {c}' for n,c in settings] if ax is ax1 else [])
  ax.set_xlabel(r'Point-query weight $\theta$',labelpad=3)
  ax.axhline(2.5,color='white',lw=1.2)
  for spine in ax.spines.values():spine.set_visible(False)
  ax.tick_params(length=0)
  title(ax,label,heading)
 ax1.set_ylabel('Owners, colluders',labelpad=3)
 for i,j in zip(*np.where(mats[0]>mats[1])):
  ax1.add_patch(Rectangle((j-.49,i-.49),.98,.98,fill=False,edgecolor=C['accent'],lw=1.0))
 x=arr(s,'uniform_loss_over_E0');y=arr(s,'harmonic_loss_over_E0');special=np.asarray([r['general_only_highlight']=='1' for r in s])
 tie=np.isclose(x,y,atol=1e-7)
 ax3.fill_between([0,1],[0,0],[0,1],color=C['H'],alpha=.045)
 ax3.plot([0,1],[0,1],color='#ADB6BE',lw=.8,ls=(0,(3,3)))
 ax3.scatter(x[~special],y[~special],s=12,c=np.where(tie[~special],C['I'],C['H']),edgecolors='white',linewidths=.25,alpha=.7,zorder=3)
 ax3.scatter(x[special],y[special],s=22,c=C['accent'],marker='D',edgecolors='white',linewidths=.4,zorder=4)
 ax3.text(.03,.98,'8 additional\nactivating cases',ha='left',va='top',color=C['accent'],fontsize=7.6,weight='bold',transform=ax3.transAxes)
 ax3.annotate('119 ties',xy=(1,1),xytext=(.58,.92),fontsize=7,color=C['muted'],arrowprops={'arrowstyle':'-','lw':.6,'color':C['muted']})
 ax3.set(xlim=(-.025,1.055),ylim=(-.025,1.065),xticks=[0,.5,1],yticks=[0,.5,1])
 ax3.set_xlabel(r'Uniform loss / $E_0$',labelpad=3);ax3.set_ylabel(r'Harmonic loss / $E_0$',labelpad=2)
 title(ax3,'c','Allocation loss');clean(ax3)

 assert special.sum()==8 and sum(int(r['orders_with_strict_gain']) for r in a)==97 and sum(int(r['orders_with_strict_gain']) for r in b)==89
 AUDIT['annotations']['activation']={'all_scatter_rows':len(s),'nonuniform_only':int(special.sum()),'general':97,'uniform':89,'ties':int(tie.sum())}
 save(fig,'activation',out)

def local(out):
 a=rows('fig2_local_gap','panel_a_triangle_brackets.csv');b=rows('fig2_local_gap','panel_b_candidate_excess_summary.csv')
 fig=plt.figure(figsize=(CW,2.62))
 ax=axes(fig,[.66,1.74,2.65,.55]);title(ax,'a','Cubic approximation order')
 x=arr(a,'tau');y=arr(a,'normalized_gap_mid');lo=arr(a,'normalized_gap_lower');hi=arr(a,'normalized_gap_upper')
 ax.errorbar(x,y,yerr=np.maximum(0,np.stack([y-lo,hi-y])),color=C['H'],marker='o',ms=3.5,capsize=2,lw=1.15,zorder=3)
 ax.axhline(1/32,color=C['muted'],ls=(0,(3,2)),lw=.8)
 ax.set_xscale('log',base=2);ax.set_xticks([1/128,1/32,1/8],['1/128','1/32','1/8'])
 ax.set_ylim(.03105,.0336);ax.set_yticks([.03125,.03225,.03325],['.03125','.03225','.03325'])
 ax.set_ylabel(r'Gap / $\tau^3$',labelpad=3);ax.text(.98,.09,'limit 1/32',transform=ax.transAxes,fontsize=7.1,color=C['muted'],ha='right')
 clean(ax)
 ax=axes(fig,[.66,.40,2.65,.86]);title(ax,'b','H candidate excess')
 hs=[]
 for family,(color,marker,name) in FAM.items():
  v=[r for r in b if r['family']==family];xx=arr(v,'tau');yy=arr(v,'plotted_center_percent')
  ax.fill_between(xx,arr(v,'band_low_percent'),arr(v,'band_high_percent'),color=color,alpha=.12,lw=0)
  ax.plot(xx,yy,color=color,marker=marker,ms=3.6,lw=1.1,markeredgewidth=.6)
  hs.append(handle(name,color,marker))
 ax.set_xscale('log',base=2);ax.set_xticks([1/16,1/4,1/2,2],['1/16','1/4','1/2','2'])
 ax.set_ylim(-.06,1.4);ax.set_yticks([0,.5,1]);ax.set_xlabel(r'Total edge-variance budget $\tau$',labelpad=3);ax.set_ylabel(r'Excess / $E_0$ (%)',labelpad=3)
 ax.annotate(r'$\leq 0.0261\%$ at $\tau\leq 1/2$',xy=(.5,.027),xytext=(.08,.57),fontsize=7.5,color=C['ink'],arrowprops={'arrowstyle':'-','lw':.7,'color':C['muted']})
 clean(ax)
 ax.legend(handles=hs,loc='upper left',bbox_to_anchor=(.0,1.02),ncol=2,fontsize=6.9,columnspacing=.9,labelspacing=.2)
 AUDIT['annotations']['local_gap']={'small_budget_excess_percent_upper':max(f(r,'band_high_percent') for r in b if f(r,'tau')<=.5),'band_kind':'objective brackets and workload variation, not confidence intervals'}
 save(fig,'local_gap',out)

def times(ax,data,methods):
 marks={'H':'o','U':'s','LP':'^','FULL':'D'}
 for method in methods:
  r=sorted([r for r in data if r['method']==method],key=lambda r:f(r,'n_owners'))
  x=arr(r,'n_owners');y=arr(r,'median_seconds')
  ax.fill_between(x,arr(r,'min_seconds'),arr(r,'max_seconds'),color=C[method],alpha=.12,lw=0)
  ax.plot(x,y,color=C[method],marker=marks[method],ms=3.5,lw=1.4 if method=='H' else 1.0,markerfacecolor=C[method] if method=='H' else 'white',markeredgewidth=.8,zorder=4 if method=='H' else 3,label=method)
 ax.set_xscale('log',base=2);ax.set_yscale('log');ax.set_xlabel('Owners',labelpad=3);clean(ax)

def scale(out):
 a=rows('fig3_scale','panel_a_sparse_planning_times.csv');b=rows('fig3_scale','panel_b_full_comparison_times.csv');c=rows('fig3_scale','panel_c_loss_at_1024.csv')
 fig=plt.figure(figsize=(W,1.94))
 ax=axes(fig,[.45,.39,1.83,1.20]);times(ax,a,['U','H','LP']);title(ax,'a','Sparse planning')
 ax.set_xticks([32,128,512,1024],['32','128','512','1024']);ax.set_ylabel('Planning time (s)',labelpad=3)
 ax.set_ylim(.15,32);ax.set_yticks([.2,1,10],['0.2','1','10']);ax.legend(loc='upper left',fontsize=7.1,handlelength=1.25,labelspacing=.16)
 h1024=next(r for r in a if r['method']=='H' and r['n_owners']=='1024')
 ax.text(.98,.065,f"H: {f(h1024,'min_seconds'):.2f}-{f(h1024,'max_seconds'):.2f} s",ha='right',transform=ax.transAxes,color=C['H'],fontsize=7.4,weight='bold')
 ax=axes(fig,[2.81,.39,1.83,1.20]);times(ax,b,['U','H','FULL']);title(ax,'b','Full comparison')
 ax.set_xticks([16,32,64,128],['16','32','64','128']);ax.set_ylim(.25,300);ax.set_yticks([1,10,100],['1','10','100']);ax.legend(loc='upper left',fontsize=7.1,handlelength=1.25,labelspacing=.16)
 full128=f(next(r for r in b if r['method']=='FULL' and r['n_owners']=='128'),'median_seconds'); h128=f(next(r for r in b if r['method']=='H' and r['n_owners']=='128'),'median_seconds'); speed=full128/h128
 ax.text(.99,.40,f'At 128 owners:\nFULL {full128:.1f} s; H {h128:.2f} s',ha='right',transform=ax.transAxes,color=C['H'],fontsize=7.4,weight='bold')
 ax=axes(fig,[5.28,.39,1.65,1.20]);title(ax,'c','Loss at 1,024')
 families=['class','range','mixed','iid'];names=['Category','Range','Mixed','IID']
 for i,fam in enumerate(families):
  u=next(r for r in c if r['family']==fam and r['method']=='U');h=next(r for r in c if r['family']==fam and r['method']=='H')
  xv=[f(u,'loss_over_E0'),f(h,'loss_over_E0')]
  ax.plot(xv,[i,i],color='#C9CED3',lw=1.4)
  ax.scatter(xv[0],i,s=19,facecolors='white',edgecolors=C['U'],marker='s',linewidths=1,zorder=4)
  ax.scatter(xv[1],i,s=19,c=C['H'],marker='o',linewidths=.5,edgecolors='white',zorder=5)
 ax.set(xlim=(-.03,1.06),ylim=(3.5,-.65),yticks=range(4),yticklabels=names,xticks=[0,.5,1])
 ax.set_xlabel(r'Loss / $E_0$ (lower is better)',labelpad=3);clean(ax,'x')
 ax.legend(handles=[handle('U',C['U'],'s','None',True),handle('H',C['H'],'o','None')],loc='lower left',bbox_to_anchor=(.01,.0),ncol=2,fontsize=7.1)
 AUDIT['annotations']['planning_speedup']={'n_owners':128,'ratio_of_medians_FULL_over_H':speed,'FULL_direct_rows_at_128':3,'H_rows_at_128':4,'not_pairwise_speedup':True}
 save(fig,'scale',out)

def grouping(out):
 a=rows('fig4_grouping','panel_a_categories_frontier.csv');b=rows('fig4_grouping','panel_b_ranges_frontier.csv');c=rows('fig4_grouping','panel_c_paired_plan_changes.csv')
 fig=plt.figure(figsize=(W,2.05))
 style={'Fixed U':('s','--'),'Adaptive U':('s','-'),'Adaptive H':('o','-'),'Portfolio':('D','-')}
 hs=[]
 for method,(mark,ls) in style.items():hs.append(handle(method,C[method],mark,ls,method!='Portfolio'))
 fig.legend(handles=hs,loc='upper left',bbox_to_anchor=(.035,1.005),ncol=4,fontsize=7.2)
 for box,data,label,text in [([.46,.39,1.78,1.22],a,'a','Categories'),([2.79,.39,1.78,1.22],b,'b','Ranges')]:
  ax=axes(fig,box)
  for method,(mark,ls) in style.items():
   v=sorted([r for r in data if r['series']==method],key=lambda r:f(r,'price'))
   ax.plot(arr(v,'max_host_kib'),arr(v,'loss_over_E0'),color=C[method],ls=ls,marker=mark,ms=4 if method=='Portfolio' else 4.2,
    markerfacecolor=C[method] if method=='Portfolio' else 'white',markeredgewidth=.8,lw=1.25 if method=='Portfolio' else .95,zorder=5 if method=='Portfolio' else 3)
  title(ax,label,text);ax.set_xlabel('Max-host traffic (KiB)',labelpad=3);ax.set_ylabel(r'Loss / $E_0$',labelpad=3)
  if data is a:ax.set(xlim=(535,730),ylim=(.16,1.06),xticks=[550,625,700],yticks=[.2,.6,1])
  else:ax.set(xlim=(2150,2375),ylim=(.36,.48),xticks=[2200,2300],yticks=[.36,.40,.44,.48])
  clean(ax)
 ax=axes(fig,[5.25,.39,1.67,1.22]);title(ax,'c','Paired plan gains')
 ax.axvspan(0,85,color=C['H'],alpha=.035,lw=0)
 for i,fam in enumerate(['class','range','mixed','iid']):
  v=[r for r in c if r['family']==fam]
  for metric,offset,color,mark in [('mse_reduction_percent',-.12,C['H'],'o'),('max_host_byte_reduction_percent',.12,C['U'],'s')]:
   values=arr(v,metric);y=i+offset+np.linspace(-.045,.045,len(v))
   ax.scatter(values,y,s=15,edgecolors=color,facecolors=color if mark=='o' else 'white',marker=mark,linewidths=.65,alpha=.65,zorder=3)
   med=np.median(values);ax.plot([med,med],[i+offset-.085,i+offset+.085],color=C['ink'],lw=1.25,zorder=5)
 ax.set(yticks=range(4),yticklabels=['Category','Range','Mixed','IID'],ylim=(3.5,-.65),xlim=(-36,85),xticks=[-25,0,25,50,75])
 ax.axvline(0,color='#8E9AA5',lw=.7);ax.set_xlabel('Reduction vs. fixed U (%)',labelpad=3);clean(ax,'x')
 fig.legend(handles=[handle('MSE',C['H'],'o','None'),handle('Host bytes',C['U'],'s','None',True)],loc='upper right',bbox_to_anchor=(.99,1.005),ncol=2,fontsize=7.1,columnspacing=.75,handletextpad=.3)
 save(fig,'grouping',out)

def finite(out):
 a=rows('fig5_finite_utility','panel_a_intel_utility.csv');b=rows('fig5_finite_utility','panel_b_electricity_utility.csv');c=rows('fig5_finite_utility','panel_c_paired_H_minus_U.csv')
 fig=plt.figure(figsize=(W,2.18));hs=[handle('I',C['I'],'^','None'),handle('U',C['U'],'s','None',True),handle('H',C['H'],'o','None'),Line2D([],[],color=C['muted'],marker='|',markersize=7,ls='None',label='Ideal loss')]
 fig.legend(handles=hs,loc='upper left',bbox_to_anchor=(.07,1.0),ncol=4,fontsize=7.3)
 fams=['groupby','mixed','range','sum'];labels=['GROUP BY','Mixed','Range','SUM']
 for box,data,label,text in [([.66,.40,1.58,1.35],a,'a','Intel'),([2.90,.40,1.58,1.35],b,'b','Electricity')]:
  ax=axes(fig,box);title(ax,label,text)
  ax.axhspan(-.4,.4,color=C['H'],alpha=.045,lw=0)
  for i,fam in enumerate(fams):
   for m,off,mk in [('I',-.19,'^'),('U',0,'s'),('H',.19,'o')]:
    r=next(r for r in data if r['family']==fam and r['method']==m);x=f(r,'weighted_mse_mean')
    ax.errorbar(x,i+off,xerr=[[x-f(r,'ci_low')],[f(r,'ci_high')-x]],fmt=mk,color=C[m],ms=3.4,
     markerfacecolor='white' if m=='U' else C[m],markeredgewidth=.7,capsize=1.6,elinewidth=.8,lw=0,zorder=4 if m=='H' else 3)
    ax.plot(f(r,'ideal_normalized_error'),i+off,marker='|',color=C[m],ms=6,mew=.75,zorder=2,alpha=.65)
  ax.set(yticks=range(4),yticklabels=labels,xlim=(-.04,1.2),ylim=(3.48,-.60),xticks=[0,.5,1])
  ax.set_xlabel(r'Weighted MSE / $E_{\mathrm{ind}}^{(d)}$',labelpad=4);clean(ax,'x')
  if data is a:
   h=next(r for r in a if r['family']=='groupby' and r['method']=='H');u=next(r for r in a if r['family']=='groupby' and r['method']=='U')
   gain=100*(1-f(h,'weighted_mse_mean')/f(u,'weighted_mse_mean'))
   ax.text(.96,.71,f'{gain:.1f}% lower',ha='right',va='center',transform=ax.transAxes,color=C['H'],fontsize=7.6,weight='bold')
 ax=axes(fig,[5.30,.40,1.63,1.35]);title(ax,'c','Paired H - U')
 order=[('intel',fa) for fa in fams]+[('electricity',fa) for fa in fams]
 ax.axvspan(-32,0,color=C['H'],alpha=.045,lw=0);ax.axvline(0,color='#88949F',ls=(0,(3,2)),lw=.8)
 for i,(ds,fam) in enumerate(order):
  r=next(r for r in c if r['dataset']==ds and r['family']==fam);x=f(r,'difference_percent_points');lo=f(r,'ci_low_percent_points');hi=f(r,'ci_high_percent_points')
  col=C['H'] if hi<0 else C['U'] if lo>0 else C['muted']
  ax.errorbar(x,i,xerr=[[x-lo],[hi-x]],fmt='o',color=col,ms=3.6,capsize=1.6,elinewidth=.9)
 ax.axhline(3.5,color=C['grid'],lw=.6)
 ax.set(yticks=range(8),yticklabels=['Int Group','Int Mixed','Int Range','Int SUM','El Group','El Mixed','El Range','El SUM'],ylim=(7.5,-.6),xlim=(-33,30),xticks=[-25,0,25])
 ax.set_xlabel(r'$(H-U)/E_{\mathrm{ind}}^{(d)}$ (pp)',labelpad=4);clean(ax,'x')
 AUDIT['annotations']['finite_report_groupby_gain_percent']=gain
 save(fig,'finite_utility',out)

def physical(out):
 a=rows('fig6_physical_execution','panel_a_matched_host_traffic.csv');b=rows('fig6_physical_execution','panel_b_matched_online_time.csv');c=rows('fig6_physical_execution','panel_c_partial_reuse.csv')
 fig=plt.figure(figsize=(W,2.22))
 ax=axes(fig,[.72,.40,1.84,1.40]);title(ax,'a','Application traffic')
 for i,r in enumerate(a):
  fixed=f(r,'fixed_u_median_kib');adaptive=f(r,'adaptive_median_kib')
  ax.plot([fixed,adaptive],[i,i],color='#C5CDD2',lw=1.0)
  for prefix,x,col,mk in [('fixed_u',fixed,C['U'],'s'),('adaptive',adaptive,C['H'],'o')]:
   ax.errorbar(x,i,xerr=[[x-f(r,prefix+'_min_kib')],[f(r,prefix+'_max_kib')-x]],fmt=mk,color=col,markerfacecolor='white' if prefix=='fixed_u' else col,ms=3.6,capsize=1.5,elinewidth=.7)
 ax.set(yticks=range(8),yticklabels=[r['row_label'] for r in a],ylim=(7.5,-.5),xlim=(300,3550),xticks=[1000,2000,3000]);ax.set_xlabel('Max-host traffic (KiB)',labelpad=3);clean(ax,'x');ax.axhline(3.5,color=C['grid'],lw=.65)
 fig.legend(handles=[handle('Fixed U',C['U'],'s','None',True),handle('Adaptive',C['H'],'o','None')],loc='upper left',bbox_to_anchor=(.075,1.0),ncol=2,fontsize=7.3)
 ax=axes(fig,[2.91,.40,1.75,1.40]);title(ax,'b','Online time')
 ax.axvspan(.90,1,color=C['H'],alpha=.045,lw=0)
 for i,r in enumerate(b):
  x=f(r,'ratio_median');ax.errorbar(x,i,xerr=[[x-f(r,'ratio_min')],[f(r,'ratio_max')-x]],fmt='o',color=C['H'],ms=3.5,capsize=1.8,elinewidth=.8)
 ax.axvline(1,color='#88949F',ls=(0,(3,2)),lw=.8);ax.axhline(3.5,color=C['grid'],lw=.65)
 ax.set(yticks=range(8),yticklabels=[],ylim=(7.5,-.5),xlim=(.73,1.82),xticks=[.8,1,1.4,1.8]);ax.set_xlabel('Adaptive / fixed U',labelpad=3);clean(ax,'x')
 ax=axes(fig,[5.42,.63,1.49,1.17]);title(ax,'c','Reuse savings')
 gains=[]
 raw_pairs=json.loads((ROOT/'data/fig6_physical_execution/reuse_pairs.json').read_text())['metrics']
 for i,r in enumerate(c):
  key=['max_application_kib','max_tls_kib','online_seconds'][i]
  ratios=np.asarray(raw_pairs[key],dtype=float)
  assert len(ratios)==10 and abs(np.median(ratios)-f(r,'ratio_median'))<1e-12
  savings=100*(1-1/ratios)
  val=float(np.median(savings));lo=float(min(savings));hi=float(max(savings));gains.append(val)
  ax.barh(i,val,height=.33,color=C['H'],alpha=.85,zorder=3)
  ax.errorbar(val,i,xerr=[[val-lo],[hi-val]],fmt='none',ecolor=C['ink'],capsize=2,elinewidth=.8,zorder=4)
  ax.text(max(val,hi)+1.8,i,f'{val:.1f}%',va='center',color=C['H'],weight='bold',fontsize=7.5)
 ax.set(yticks=range(3),yticklabels=['App. bytes','TLS bytes','Time'],ylim=(2.55,-.6),xlim=(0,57),xticks=[0,20,40]);ax.set_xlabel('Saved vs. no reuse (%)',labelpad=3);clean(ax,'x')
 fig.text(.759,.055,'Same allocation and routes',fontsize=7.0,color=C['muted'])
 AUDIT['annotations']['reuse_savings']={'formula':'median_i [100 * (1 - 1 / (no_reuse_i / reuse_i))]' ,'metrics':[r['metric_label'] for r in c],'median_savings_percent':gains,'range_transformation':'transform all ten paired values, then take median and full range','paired_repetitions':10}
 save(fig,'physical_execution',out)

def main():
 ap=argparse.ArgumentParser();ap.add_argument('--out',type=Path,default=ROOT/'output');args=ap.parse_args();args.out.mkdir(parents=True,exist_ok=True)
 for func in [activation,local,scale,grouping,finite,physical]:func(args.out)
 (args.out/'plot_validation.json').write_text(json.dumps(AUDIT,indent=2))
 print(json.dumps({'panels':len(AUDIT['panels']),'source_rows':sum(x['rows'] for x in AUDIT['panels'].values()),'annotations':AUDIT['annotations'],'boundary_warnings':AUDIT['artist_boundary_warnings']},indent=2))
if __name__=='__main__':main()
