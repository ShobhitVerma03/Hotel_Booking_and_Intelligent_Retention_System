from pathlib import Path
import json, joblib, pandas as pd
from sklearn.compose import ColumnTransformer
from sklearn.pipeline import Pipeline
from sklearn.preprocessing import OneHotEncoder
from sklearn.ensemble import RandomForestClassifier
from sklearn.model_selection import train_test_split
from sklearn.metrics import accuracy_score,precision_score,recall_score,f1_score,roc_auc_score,confusion_matrix
from backend.ml.data.development.generate_dataset import generate
ART=Path('backend/ml/artifacts'); MODEL=ART/'risk_model.joblib'
def train():
 p=generate(); df=pd.read_csv(p); X=df.drop(columns=['cancelled','customer_id']); y=df.cancelled; cat=X.select_dtypes(include='object').columns.tolist(); pre=ColumnTransformer([('cat',OneHotEncoder(handle_unknown='ignore'),cat)],remainder='passthrough'); x1,x2,y1,y2=train_test_split(X,y,test_size=.25,random_state=42,stratify=y); pipe=Pipeline([('pre',pre),('model',RandomForestClassifier(n_estimators=120,random_state=42,class_weight='balanced'))]); pipe.fit(x1,y1); pr=pipe.predict_proba(x2)[:,1]; m={'model_type':'RandomForestClassifier','model_version':'synthetic-dev-v1','dataset_type':'SYNTHETIC_DEVELOPMENT','features':X.columns.tolist(),'target':'cancelled','metrics':{'accuracy':accuracy_score(y2,pr>=.5),'precision':precision_score(y2,pr>=.5),'recall':recall_score(y2,pr>=.5),'f1':f1_score(y2,pr>=.5),'roc_auc':roc_auc_score(y2,pr),'confusion_matrix':confusion_matrix(y2,pr>=.5).tolist()}}; ART.mkdir(parents=True,exist_ok=True); joblib.dump(pipe,MODEL); (ART/'risk_model.metadata.json').write_text(json.dumps(m,indent=2)); return m
if __name__=='__main__': print(json.dumps(train(),indent=2))
