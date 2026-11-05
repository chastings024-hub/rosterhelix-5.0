"""5.0E.4 rolling-origin research validation. Does not alter production."""
from rh_model_e3 import evaluate_heldout
VERSION='5.0E.4-rolling-origin-v1'

def evaluate_rolling(conn, start, end, scoring, projection_fn, limit=900, lookback=3):
    if scoring not in ('ppr','half','standard'): raise ValueError('Unsupported scoring')
    if not 2004<=start<=end<=2100 or end-start>3: raise ValueError('Choose 1–4 consecutive test seasons')
    if not 1<=lookback<=4: raise ValueError('Lookback must be 1–4 seasons')
    if not 100<=limit<=3000: raise ValueError('Limit must be 100–3000')
    tests=[]
    for year in range(start,end+1):
        years=list(range(year-lookback,year))
        result=evaluate_heldout(conn,years,year,scoring,projection_fn,limit)
        tests.append(result)
    valid=[t for t in tests if t.get('status')=='evaluated' and t.get('holdout',{}).get('n')]
    n=sum(t['holdout']['n'] for t in valid)
    existing=sum(t['holdout']['production_mae']*t['holdout']['n'] for t in valid)/n if n else None
    candidate=sum(t['holdout']['candidate_mae']*t['holdout']['n'] for t in valid)/n if n else None
    wins=sum(t['holdout']['delta_mae']>0 for t in valid)
    return {'version':VERSION,'scoring':scoring,'test_seasons':list(range(start,end+1)),
            'lookback_training_seasons':lookback,'scan_limit_per_season':limit,
            'summary':{'evaluated_seasons':len(valid),'requested_seasons':end-start+1,
                       'player_games':n,'production_mae':round(existing,4) if n else None,
                       'candidate_mae':round(candidate,4) if n else None,
                       'delta_mae':round(existing-candidate,4) if n else None,
                       'seasons_candidate_wins':wins},
            'results':tests,'production_model_unchanged':True,
            'promotion_recommendation':'research_only_no_automatic_promotion',
            'methodology':'Rolling-origin evaluation: for each test year, recipe selection uses only earlier years. Test year is not used for its own model selection. Each game uses prior weeks only.',
            'limitations':['Model designs were informed by historical observations; these are not prospectively unseen seasons',
                           'Input scan limit may reduce samples; early weeks and missed games excluded',
                           'No snap, route, injury, weather, or coverage features imported',
                           'No formal multiple-testing correction or calibrated uncertainty across holdouts',
                           'Historical validation does not guarantee live fantasy performance']}
