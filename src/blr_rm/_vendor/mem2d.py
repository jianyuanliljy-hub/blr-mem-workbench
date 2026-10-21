from __future__ import annotations

from dataclasses import dataclass
import time
import numpy as np
from scipy.optimize import minimize

POSITIVE_FLOOR=1e-10


def interpolation_matrix(target_times, grid_times):
    target_times=np.asarray(target_times,float); grid_times=np.asarray(grid_times,float)
    if target_times.min()<grid_times.min()-1e-10 or target_times.max()>grid_times.max()+1e-10:
        raise ValueError("continuum grid must cover all t_L - tau")
    right=np.searchsorted(grid_times,target_times,side="right"); right=np.clip(right,1,len(grid_times)-1)
    left=right-1; frac=(target_times-grid_times[left])/(grid_times[right]-grid_times[left])
    M=np.zeros((len(target_times),len(grid_times)),float); rows=np.arange(len(target_times))
    M[rows,left]=1-frac; M[rows,right]+=frac
    return M


def geometric_default_1d(values):
    p=np.clip(np.asarray(values,float),POSITIVE_FLOOR,None); q=np.empty_like(p)
    q[1:-1]=np.sqrt(p[:-2]*p[2:]); q[0]=np.sqrt(p[0]*p[1]); q[-1]=np.sqrt(p[-2]*p[-1]); return q


def geometric_default_2d(values,smoothness_ratio=1.0):
    p=np.clip(np.asarray(values,float),POSITIVE_FLOOR,None)
    qv=np.empty_like(p); qt=np.empty_like(p)
    qv[1:-1]=np.sqrt(p[:-2]*p[2:]); qv[0]=np.sqrt(p[0]*p[1]); qv[-1]=np.sqrt(p[-2]*p[-1])
    qt[:,1:-1]=np.sqrt(p[:,:-2]*p[:,2:]); qt[:,0]=np.sqrt(p[:,0]*p[:,1]); qt[:,-1]=np.sqrt(p[:,-2]*p[:,-1])
    wv=float(smoothness_ratio)/(1.0+float(smoothness_ratio)); wt=1.0/(1.0+float(smoothness_ratio))
    return (qv**wv)*(qt**wt)


def entropy_positive(image,default):
    p=np.clip(np.asarray(image,float),POSITIVE_FLOOR,None); q=np.clip(np.asarray(default,float),POSITIVE_FLOOR,None)
    lr=np.log(p/q); return float(np.sum(p-q-p*lr)), -lr


def component_test(grad_chi2,grad_s,values):
    active=np.asarray(values)>100*POSITIVE_FLOOR
    if not active.any(): return 0.0
    a=np.asarray(grad_chi2)[active]; b=np.asarray(grad_s)[active]
    na=np.linalg.norm(a); nb=np.linalg.norm(b)
    if na<1e-14 and nb<1e-14: return 0.0
    if na<1e-14 or nb<1e-14: return 1.0
    return float(1.0-np.clip(np.dot(a,b)/(na*nb),-1,1))


@dataclass
class MEM2DResult:
    psi: np.ndarray
    continuum: np.ndarray
    l_bg: np.ndarray
    l_pred: np.ndarray
    history: list[dict]
    runtime_s: float
    success: bool
    diagnostics: dict


class MEM2DProblem:
    """Modular form of the user's 2D MEM objective.

    Parameters are [positive Psi(v,tau), positive C(t), positive L0(v)].
    The objective is chi2_C + chi2_L - alpha_map*S_map - alpha_C*S_C - alpha_Lbg*S_Lbg.
    """
    def __init__(self,t_c,c_obs,c_err,t_l,l_obs,l_err,velocities,delays,time_mask=None,c0=None):
        self.t_c=np.asarray(t_c,float); self.c_obs=np.asarray(c_obs,float); self.c_err=np.asarray(c_err,float)
        self.t_l=np.asarray(t_l,float); self.l_obs=np.asarray(l_obs,float); self.velocities=np.asarray(velocities,float); self.delays=np.asarray(delays,float)
        self.nv=len(self.velocities); self.nt=len(self.t_l); self.ntau=len(self.delays); self.nc=len(self.t_c); self.dtau=float(self.delays[1]-self.delays[0])
        if np.isscalar(l_err): self.l_err=np.full_like(self.l_obs,float(l_err))
        else:
            arr=np.asarray(l_err,float); self.l_err=np.broadcast_to(arr,self.l_obs.shape).copy()
        self.time_mask=np.ones(self.nt,bool) if time_mask is None else np.asarray(time_mask,bool)
        self.obs_weight=self.time_mask[None,:].astype(float)/(self.l_err**2)
        self.c0=float(np.mean(self.c_obs) if c0 is None else c0)
        req=(self.t_l[:,None]-self.delays[None,:]).reshape(-1); self.M_req=interpolation_matrix(req,self.t_c)
        self.map_slice=slice(0,self.nv*self.ntau); self.c_slice=slice(self.nv*self.ntau,self.nv*self.ntau+self.nc); self.bg_slice=slice(self.nv*self.ntau+self.nc,self.nv*self.ntau+self.nc+self.nv)
    def unpack(self,w):
        return w[self.map_slice],w[self.c_slice],w[self.bg_slice]
    def predict(self,pflat,c,bg):
        p=pflat.reshape(self.nv,self.ntau); dc=(self.M_req@(c-self.c0)).reshape(self.nt,self.ntau)
        return p@dc.T*self.dtau+bg[:,None],dc
    def chi2_grad(self,w):
        pflat,c,bg=self.unpack(w)
        rawc=c-self.c_obs; wc=rawc/(self.c_err**2); chi_c=float(np.sum((rawc/self.c_err)**2)); gc=2*wc
        lp,dc=self.predict(pflat,c,bg); rawl=lp-self.l_obs; wl=rawl*self.obs_weight; chi_l=float(np.sum(rawl*rawl*self.obs_weight))
        p=pflat.reshape(self.nv,self.ntau)
        gm=(2*wl@dc*self.dtau).reshape(-1)
        gdc=2*wl.T@p*self.dtau; gc=gc+self.M_req.T@gdc.reshape(-1)
        gb=2*np.sum(wl,axis=1)
        return chi_c,chi_l,(gm,gc,gb),lp


def reconstruct_mem2d(problem: MEM2DProblem, cfg: dict) -> MEM2DResult:
    t0=time.perf_counter(); nv,ntau,nc=problem.nv,problem.ntau,problem.nc
    alpha_map=float(cfg.get("alpha_map",125000)); alpha_c=float(cfg.get("alpha_c",200)); alpha_bg=float(cfg.get("alpha_lbg",10))
    smooth=float(cfg.get("smoothness_ratio",1)); outer_max=int(cfg.get("default_iterations",6)); opt_max=int(cfg.get("optimizer_maxiter",1200)); damping=float(cfg.get("default_damping",0.5))
    cycles_max=int(cfg.get("coordinate_cycles",20)); test_thr=float(cfg.get("test_threshold",1e-4)); qgrad_thr=float(cfg.get("q_gradient_threshold",5e-3))
    p0=np.full(nv*ntau,1.0/(nv*ntau)); c0=np.clip(problem.c_obs,POSITIVE_FLOOR,None); bg0=np.clip(np.percentile(problem.l_obs[:,problem.time_mask],10,axis=1),1e-6,None)
    w=np.concatenate([p0,c0,bg0]); qmap=geometric_default_2d(p0.reshape(nv,ntau),smooth).reshape(-1); qc=geometric_default_1d(c0); qbg=geometric_default_1d(bg0)
    scales=np.concatenate([np.full(nv*ntau,1.0/(nv*ntau)),np.full(nc,max(float(np.median(problem.c_err)),1e-3)),np.full(nv,max(float(np.median(bg0)),0.1))])
    bounds_all=[(POSITIVE_FLOOR/s,None) for s in scales]
    history=[]; all_success=True

    def obj_full(wcur):
        p,c,bg=problem.unpack(wcur); cc,cl,g,_=problem.chi2_grad(wcur)
        sm,gsm=entropy_positive(p,qmap); sc,gsc=entropy_positive(c,qc); sb,gsb=entropy_positive(bg,qbg)
        Q=cc+cl-alpha_map*sm-alpha_c*sc-alpha_bg*sb
        grad=np.concatenate([g[0]-alpha_map*gsm,g[1]-alpha_c*gsc,g[2]-alpha_bg*gsb])
        return Q,grad,(gsm,gsc,gsb),g

    for outer in range(outer_max):
        inner_converged=False; block_nit=0; block_success=True
        for cyc in range(cycles_max):
            # Map and C blocks use L-BFGS-B; background gets a short L-BFGS-B block as well for simplicity/stability.
            for block in (problem.map_slice,problem.c_slice,problem.bg_slice):
                fixed=w.copy(); bscale=scales[block]
                def f(z,block=block,fixed=fixed,bscale=bscale):
                    trial=fixed.copy(); trial[block]=z*bscale; Q,g,_,_=obj_full(trial); return Q,g[block]*bscale
                res=minimize(f,w[block]/bscale,jac=True,method="L-BFGS-B",bounds=bounds_all[block],
                             options={"maxiter":opt_max if block==problem.map_slice else max(100,opt_max//4),"ftol":1e-11,"gtol":1e-8,"maxcor":20,"maxls":40})
                w[block]=res.x*bscale; block_nit+=int(res.nit); block_success=block_success and bool(res.success)
            Q,gS,gchi=obj_full(w)[0],obj_full(w)[2],obj_full(w)[3]
            p,c,bg=problem.unpack(w)
            tests={"map":component_test(gchi[0],gS[0],p),"C":component_test(gchi[1],gS[1],c),"L_bg":component_test(gchi[2],gS[2],bg)}
            qrels={}
            for name,vals,gd,gs,a in (("map",p,gchi[0],gS[0],alpha_map),("C",c,gchi[1],gS[1],alpha_c),("L_bg",bg,gchi[2],gS[2],alpha_bg)):
                active=vals>100*POSITIVE_FLOOR; qg=gd[active]-a*gs[active]; den=max(np.linalg.norm(gd[active]),np.linalg.norm(a*gs[active]),1e-14); qrels[name]=float(np.linalg.norm(qg)/den)
            if max(tests.values())<=test_thr and max(qrels.values())<=qgrad_thr:
                inner_converged=True; break
        cc,cl,_,lp=problem.chi2_grad(w); p,c,bg=problem.unpack(w)
        target_map=geometric_default_2d(p.reshape(nv,ntau),smooth).reshape(-1); target_c=geometric_default_1d(c); target_bg=geometric_default_1d(bg)
        change=max(float(np.sqrt(np.mean(np.log(np.clip(a,POSITIVE_FLOOR,None)/np.clip(b,POSITIVE_FLOOR,None))**2))) for a,b in ((target_map,qmap),(target_c,qc),(target_bg,qbg)))
        history.append({"outer":outer+1,"cycles":cyc+1,"block_nit":block_nit,"optimizer_success":int(block_success),"inner_converged":int(inner_converged),"chi2_C":cc,"chi2_L":cl,"reduced_chi2_C":cc/problem.nc,"reduced_chi2_L":cl/max(problem.nv*int(problem.time_mask.sum()),1),"default_change":change,**{f"TEST_{k}":v for k,v in tests.items()},**{f"qgrad_{k}":v for k,v in qrels.items()}})
        all_success=all_success and block_success
        if outer==outer_max-1: break
        def damp(q,t): return np.exp((1-damping)*np.log(np.clip(q,POSITIVE_FLOOR,None))+damping*np.log(np.clip(t,POSITIVE_FLOOR,None)))
        qmap=damp(qmap,target_map); qc=damp(qc,target_c); qbg=damp(qbg,target_bg)
    p,c,bg=problem.unpack(w); _,_,_,lp=problem.chi2_grad(w); runtime=time.perf_counter()-t0
    last = history[-1] if history else {}
    diag={"map_sum":float(np.sum(p)),"C_min":float(c.min()),"C_max":float(c.max()),"L_bg_min":float(bg.min()),"L_bg_max":float(bg.max()),"n_observed_epochs":int(problem.time_mask.sum()),"all_optimizer_success":bool(all_success),"all_finite":bool(np.isfinite(w).all() and np.isfinite(lp).all()),"outer_iterations":len(history),"final_inner_converged":bool(last.get("inner_converged",False)),"final_reduced_chi2_C":float(last.get("reduced_chi2_C",np.nan)),"final_reduced_chi2_L":float(last.get("reduced_chi2_L",np.nan)),"final_default_change":float(last.get("default_change",np.nan)),"final_TEST_map":float(last.get("TEST_map",np.nan)),"final_TEST_C":float(last.get("TEST_C",np.nan)),"final_TEST_L_bg":float(last.get("TEST_L_bg",np.nan)),"total_block_nit":int(sum(x.get("block_nit",0) for x in history))}
    # Package adapter: expose the final frozen defaults for independent diagnostics.
    diag["final_default_map"] = qmap.reshape(nv, ntau).copy()
    diag["final_default_continuum"] = qc.copy()
    diag["final_default_background"] = qbg.copy()
    return MEM2DResult(psi=p.reshape(nv,ntau),continuum=c,l_bg=bg,l_pred=lp,history=history,runtime_s=runtime,success=bool(all_success),diagnostics=diag)
