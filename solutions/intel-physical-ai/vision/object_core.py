"""Object-localized anomaly scoring and labelled calibration; never actuation."""
from __future__ import annotations
import math
import cv2
import numpy as np
MEAN=np.asarray([.485,.456,.406],dtype=np.float32)
STD=np.asarray([.229,.224,.225],dtype=np.float32)
ROI_CONFIG={'size':256,'minimum_area_fraction':.005,'maximum_objects':8,'bbox_context':.12,'mask_context':.04,'method':'otsu-border-hull-and-nearby-components','preevaluation_refinement':'Convex hull retains exterior notches; include detached foreground inside crop context. Outside-context fragments remain unqualified.'}
class CaptureRefusal(ValueError):
    """Observation unsuitable for bounded inspection."""

def extract_objects(rgb: np.ndarray) -> list[dict]:
    """No truth masks: object hull and bounded nearby foreground are scored.

    This covers exterior notches and fragments inside crop context, not unseen
    or arbitrarily distant missing material. Physical capture remains unqualified.
    """
    if rgb.dtype!=np.uint8 or rgb.ndim!=3 or rgb.shape[2]!=3:raise CaptureRefusal('Expected uint8 RGB')
    height,width=rgb.shape[:2]
    if min(height,width)<32 or height*width>20_000_000:raise CaptureRefusal('Image dimension limit')
    gray=cv2.cvtColor(rgb,cv2.COLOR_RGB2GRAY)
    _,fg=cv2.threshold(gray,0,255,cv2.THRESH_BINARY+cv2.THRESH_OTSU)
    border=np.concatenate((fg[0],fg[-1],fg[:,0],fg[:,-1]))
    if np.mean(border>0)>.5:fg=255-fg
    contours,_=cv2.findContours(fg,cv2.RETR_EXTERNAL,cv2.CHAIN_APPROX_SIMPLE)
    contours=[c for c in contours if cv2.contourArea(c)>=.005*height*width]
    contours.sort(key=lambda c:(cv2.boundingRect(c)[1],cv2.boundingRect(c)[0]))
    if not 1<=len(contours)<=8:raise CaptureRefusal(f'Object count {len(contours)} outside 1..8')
    background=np.median(np.concatenate((rgb[0],rgb[-1],rgb[:,0],rgb[:,-1]),axis=0),axis=0).astype(np.uint8)
    output=[]
    for number,contour in enumerate(contours):
        x,y,w,h=cv2.boundingRect(contour)
        if x==0 or y==0 or x+w>=width or y+h>=height:raise CaptureRefusal('Object intersects capture boundary')
        side=int(math.ceil(max(w,h)*1.24));left=int(math.floor(x+w/2-side/2));top=int(math.floor(y+h/2-side/2))
        x0=max(0,left);y0=max(0,top);x1=min(width,left+side);y1=min(height,top+side)
        crop=np.empty((side,side,3),dtype=np.uint8);crop[:]=background
        crop[y0-top:y1-top,x0-left:x1-left]=rgb[y0:y1,x0:x1]
        mask=np.zeros((height,width),dtype=np.uint8);cv2.drawContours(mask,[cv2.convexHull(contour)],-1,255,cv2.FILLED)
        # Include small detached foreground inside this object's fixed context.
        mask[y0:y1,x0:x1] |= fg[y0:y1,x0:x1]
        radius=max(1,int(math.ceil(.04*max(w,h))))
        mask=cv2.dilate(mask,cv2.getStructuringElement(cv2.MORPH_ELLIPSE,(2*radius+1,2*radius+1)))
        local=np.zeros((side,side),dtype=np.uint8);local[y0-top:y1-top,x0-left:x1-left]=mask[y0:y1,x0:x1]
        image=cv2.resize(crop,(256,256),interpolation=cv2.INTER_LINEAR)
        scoring=cv2.resize(local,(256,256),interpolation=cv2.INTER_NEAREST)>0
        if not scoring.any():raise CaptureRefusal('Empty scoring region')
        tensor=((image.astype(np.float32)/255-MEAN)/STD).transpose(2,0,1)[None].copy()
        output.append({'object_index':number,'bbox':[x,y,w,h],'square':[left,top,side],'tensor':tensor,'mask':scoring,'foreground_pixels':int(np.count_nonzero(mask))})
    return output

def object_score(anomaly_map: np.ndarray,mask: np.ndarray) -> float:
    a=np.asarray(anomaly_map,dtype=np.float32)
    if a.shape!=(1,1,256,256) or mask.shape!=(256,256) or mask.dtype!=np.bool_:raise ValueError('Anomaly map/foreground shape')
    if not np.isfinite(a).all() or not mask.any():raise ValueError('Invalid anomaly map values')
    return float(a[0,0][mask].max())

def _candidates(values: np.ndarray) -> list[float]:
    """Float64 midpoint thresholds avoid fragile one-ULP calibration boundaries."""
    vals=np.unique(np.asarray(values,dtype=np.float64))
    if len(vals)==0 or not np.isfinite(vals).all():raise ValueError('Finite calibration scores required')
    gap=max(1.,float(np.max(np.abs(vals)))*.01)
    return [float(vals[0]-gap)]+[float(a+(b-a)/2) for a,b in zip(vals[:-1],vals[1:])]+[float(vals[-1]+gap)]

def calibrate(rows: list[dict],recall_target: float=.95,false_positive_limit: float=.10) -> dict:
    if not 0<recall_target<=1 or not 0<=false_positive_limit<1:raise ValueError('Invalid targets')
    if any(r['label'] not in ('normal','anomaly') for r in rows):raise ValueError('Invalid calibration label')
    counts={k:sum(r['label']==k for r in rows) for k in ('normal','anomaly')}
    if min(counts.values())<10:raise ValueError('Insufficient labelled calibration')
    refused={k:sum(r['label']==k and r['score'] is None for r in rows) for k in counts}
    targets={'recall':recall_target,'false_positive':false_positive_limit}
    if any(refused.values()):return {'status':'UNSCORABLE_CALIBRATION','binary':None,'good':None,'defect':None,'counts':counts,'refused':refused,'feasible':False,'targets':targets}
    scores=np.asarray([r['score'] for r in rows],dtype=np.float64)
    if not np.isfinite(scores).all():raise ValueError('Nonfinite calibration score')
    defects=np.asarray([r['score'] for r in rows if r['label']=='anomaly'],dtype=np.float64)
    normals=np.asarray([r['score'] for r in rows if r['label']=='normal'],dtype=np.float64)
    required=int(math.ceil(recall_target*len(defects)-1e-12));allowed=int(math.floor(false_positive_limit*len(normals)+1e-12))
    candidates=_candidates(scores)
    good=max(t for t in candidates if int(np.count_nonzero(defects>t))>=required)
    bad=min(t for t in candidates if int(np.count_nonzero(normals>t))<=allowed)
    fp=int(np.count_nonzero(normals>good));tp=int(np.count_nonzero(defects>good))
    return {'status':'FEASIBLE' if fp<=allowed else 'INFEASIBLE','binary':good,'good':good,'defect':max(good,bad),'counts':counts,'refused':refused,'feasible':fp<=allowed,'calibration_tp':tp,'calibration_fp':fp,'targets':targets,'comparison':'float64 score > threshold; midpoint candidates; good <= lower; defect > upper','meaning':'Labelled empirical calibration, not population risk certification'}

def decide(score: float | None,calibration: dict) -> dict:
    if score is None or not math.isfinite(float(score)):return {'diagnostic':'hold','binary_defect':None,'reason':'CAPTURE_OR_INFERENCE_REFUSAL'}
    if calibration['binary'] is None:return {'diagnostic':'hold','binary_defect':None,'reason':'CALIBRATION_UNAVAILABLE'}
    lower=float(calibration['good']);upper=float(calibration['defect']);threshold=float(calibration['binary'])
    if not all(math.isfinite(x) for x in [lower,upper,threshold]) or lower>upper:raise ValueError('Invalid calibration boundaries')
    diagnostic='good' if score<=lower else 'defect' if score>upper else 'hold'
    return {'diagnostic':diagnostic,'binary_defect':bool(score>threshold),'reason':'OFFLINE_SCORE_ONLY'}

def metrics(predictions: list[dict],truth: dict[str,str],calibration: dict) -> dict:
    if len({r['image'] for r in predictions})!=len(predictions) or set(truth)!={r['image'] for r in predictions}:raise ValueError('Prediction/truth identity mismatch')
    counts={c:sum(v==c for v in truth.values()) for c in ('normal','anomaly')}
    if min(counts.values())==0 or sum(counts.values())!=len(truth):raise ValueError('Two truth classes required')
    confusion={'tp':0,'fn':0,'fp':0,'tn':0,'unscorable_normal':0,'unscorable_defect':0}
    ternary={c:{k:0 for k in ('good','defect','hold')} for c in counts};positive=[];negative=[]
    for row in predictions:
        label=truth[row['image']];d=decide(row['score'],calibration);ternary[label][d['diagnostic']]+=1
        if row['score'] is not None:(positive if label=='anomaly' else negative).append(float(row['score']))
        binary=d['binary_defect']
        if label=='anomaly':
            if binary is True:confusion['tp']+=1
            else:confusion['fn']+=1
            if binary is None:confusion['unscorable_defect']+=1
        elif binary is None:confusion['unscorable_normal']+=1
        elif binary:confusion['fp']+=1
        else:confusion['tn']+=1
    complete=confusion['unscorable_normal']+confusion['unscorable_defect']==0
    auc=sum((a>b)+.5*(a==b) for a in positive for b in negative)/(len(positive)*len(negative)) if complete else None
    recall=confusion['tp']/counts['anomaly'];fpr=confusion['fp']/counts['normal']
    passed=complete and calibration['feasible'] and recall>=.95 and fpr<=.10
    return {'counts':counts,'binary':confusion,'defect_recall':recall,'normal_false_positive_rate':fpr,'image_auroc':auc,'all_images_scored':complete,'ternary':ternary,'defective_to_good_rate':ternary['anomaly']['good']/counts['anomaly'],'normal_to_defect_rate':ternary['normal']['defect']/counts['normal'],'hold_rate':sum(c['hold'] for c in ternary.values())/len(predictions),'automatic_coverage_diagnostic':sum(c['good']+c['defect'] for c in ternary.values())/len(predictions),'offline_point_targets_met':passed,'population_or_hardware_qualified':False}
