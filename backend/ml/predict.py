from datetime import datetime, timezone
from functools import lru_cache
import json, joblib, pandas as pd
import logging
from pathlib import Path
from backend.app.core.config import get_settings

@lru_cache
def load_model():
    s=get_settings()
    try: return joblib.load(s.ml_model_path), json.loads(Path(s.ml_model_path.replace('.joblib','.metadata.json')).read_text())
    except Exception as exc: raise RuntimeError(f'ML model artifact unavailable: {exc}')

def category(score):
    s=get_settings()
    return 'LOW' if score < s.ml_low_risk_threshold else 'MEDIUM' if score < s.ml_high_risk_threshold else 'HIGH'

def predict(features):
    if features is None: return {'risk_score':None,'risk_category':'UNKNOWN','model_version':None,'prediction_timestamp':datetime.now(timezone.utc)}
    model,meta=load_model()
    frame = pd.DataFrame([features], columns=meta['features'])
    if frame.isna().any().any():
        raise ValueError('ML input is missing required features')
    positive_class = list(model.classes_).index(1)
    score=float(model.predict_proba(frame)[0][positive_class])
    logging.getLogger(__name__).info('ml.predicted category=%s probability=%.4f model=%s', category(score), score, meta['model_version'])
    return {'risk_score':score,'risk_category':category(score),'model_version':meta['model_version'],'prediction_timestamp':datetime.now(timezone.utc)}
