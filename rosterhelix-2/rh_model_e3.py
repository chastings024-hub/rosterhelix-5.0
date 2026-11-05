"""5.0E.3 research-only, training-season selected convex ensemble."""
from statistics import mean
from rh_model_e import _predictions
from rh_model_d3 import _fantasy
VERSION='5.0E.3-heldout-ensemble-v1'
FEATURES=('no_matchup','recent_only','season_only','opportunity_35','opportunity_65')
def collect(conn,year,scoring,projection_fn,limit):
 rows=[]
 games=conn.execute("SELECT * FROM player_games WHERE season=? AND pos IN ('RB','WR','TE') AND week>=4 ORDER BY week,player LIMIT ?",(year,limit)).fetchall()
 for g in games:
  week=int(g['week']); prior=conn.execute('SELECT * FROM player_games WHERE season=? AND player=? AND week<? ORDER BY week DESC',(year,g['player'],week)).fetchall()
  if len(prior)<3:continue
  try:
   base=projection_fn(conn,g['player'],year,scoring,(g['opponent'] or '').upper(),before_week=week)
   pred=_predictions(prior,base,scoring)
   rows.append({'pos':g['pos'],'actual':_fantasy(g,scoring),'pred':pred})
  except (ValueError,TypeError,KeyError,ZeroDivisionError):continue
 return rows
def forecast(r,recipe):
 feature,w=recipe;p=r['pred']['production']
 return p if feature is None else (1-w)*p+w*r['pred'][feature]
def mae(rows,recipe):return mean(abs(forecast(r,recipe)-r['actual']) for r in rows)
def metrics(rows,models):
 if not rows:return {'n':0}
 a=mean(abs(r['pred']['production']-r['actual']) for r in rows)
 b=mean(abs(forecast(r,models[r['pos']])-r['actual']) for r in rows)
 return {'n':len(rows),'production_mae':round(a,4),'candidate_mae':round(b,4),'delta_mae':round(a-b,4)}
def evaluate_heldout(conn,train_years,test_year,scoring,projection_fn,limit=1200):
 if scoring not in ('ppr','half','standard'):raise ValueError('Invalid scoring')
 if not 1<=len(train_years)<=4 or len(set(train_years))!=len(train_years) or any(y<2000 or y>=test_year for y in train_years) or not 2001<=test_year<=2100:raise ValueError('Training seasons must be unique and precede the holdout')
 if not 100<=limit<=3000:raise ValueError('Limit must be 100–3000')
 train=[r for y in train_years for r in collect(conn,y,scoring,projection_fn,limit)]
 test=collect(conn,test_year,scoring,projection_fn,limit)
 if len(train)<50 or len(test)<30:return {'version':VERSION,'status':'insufficient_data','train_n':len(train),'holdout_n':len(test),'production_model_unchanged':True}
 candidates=[(None,0)]+[(f,w) for f in FEATURES for w in (.25,.5,.75,1.)]
 global_best=min(candidates,key=lambda c:(mae(train,c),c[1]))
 models={}
 for p in ('RB','WR','TE'):
  subset=[r for r in train if r['pos']==p]
  models[p]=min(candidates,key=lambda c:(mae(subset,c),c[1])) if len(subset)>=80 else global_best
 return {'version':VERSION,'status':'evaluated','scoring':scoring,'training_seasons':train_years,'holdout_season':test_year,'scan_limit_per_season':limit,'training':metrics(train,models),'holdout':metrics(test,models),'by_position':{p:metrics([r for r in test if r['pos']==p],models) for p in models},'selected_recipes':{p:{'alternate_feature':models[p][0],'alternate_weight':models[p][1]} for p in models},'production_model_unchanged':True,'promotion_recommendation':'research_only_no_automatic_promotion','methodology':'Predefined convex blends selected using training seasons only. Each sample uses strictly earlier weeks within its season. Holdout excluded from weight selection.','limitations':['Only RB/WR/TE games with at least three prior recorded games','Missing carries, snaps, routes, injury, weather and coverage data','Holdout season may have been seen during prior human development','No automatic promotion; run additional independent validation']}
