"""Creates fictional Indian-hotel synthetic development labels only."""
from pathlib import Path
import numpy as np, pandas as pd
OUT=Path(__file__).with_name('hotel_cancellation_development.csv')
def generate(n=1500, seed=42):
 r=np.random.default_rng(seed); cities=['Delhi','Mumbai','Bengaluru','Hyderabad','Chennai','Jaipur','Goa','Pune','Kolkata']; rows=[]
 for i in range(n):
  previous=int(r.integers(0,15)); cancels=int(r.binomial(previous,.16)) if previous else 0; lead=int(r.integers(1,121)); value=int(r.integers(2500,22000)); channel=r.choice(['direct','ota','corporate']); prob=1/(1+np.exp(-(-2.3+.13*cancels+.012*lead+.5*(channel=='ota')+.35*(value>15000))))
  rows.append([f'customer_{i:04d}',r.choice(cities),r.choice(['business','leisure']),r.choice(['standard','deluxe','suite']),channel,previous,cancels,previous-cancels, cancels/previous if previous else 0, int(r.integers(2500,18000)),value,lead,int(r.integers(1,8)),int(r.integers(1,5)),int(r.integers(1,13)),int(r.integers(0,1500)),int(r.integers(0,4)),float(r.random()),r.choice(['prepaid','pay_at_hotel','card']),bool(r.integers(0,2)),int(r.random()<prob)])
 cols=['customer_id','city','hotel_type','room_type','booking_channel','previous_bookings','previous_cancellations','completed_stays','cancellation_rate','average_previous_booking_value_inr','current_booking_value_inr','lead_time_days','length_of_stay','number_of_guests','booking_month','customer_tenure_days','previous_retention_offers','previous_offer_acceptance_rate','payment_type','weekend_booking','cancelled']; pd.DataFrame(rows,columns=cols).to_csv(OUT,index=False); return OUT
if __name__=='__main__': print(generate())
