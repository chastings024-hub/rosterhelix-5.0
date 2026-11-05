"""RosterHelix 5.0E research diagnostics. Does not affect live projections.

Ablations are predefined, not optimized on evaluation data. All predictions are
walk-forward: only games strictly before the evaluated week are used.
"""
from collections import defaultdict
from statistics import mean
from rh_model_d3 import candidate_projection, _fantasy

VERSION = '5.0E-ablation-v1'
RECIPES = ('production', 'd3_candidate', 'no_matchup', 'recent_only', 'season_only', 'opportunity_35', 'opportunity_65')

def _clip(x):
    return round(max(0.0, float(x)), 2)

def _predictions(prior, base, scoring):
    multiplier = float(base.get('opponent_multiplier') or 1.0)
    baseline_unadjusted = (float(base['projected_points']) / multiplier) if multiplier else float(base['projected_points'])
    season = float(base['season_ppg'])
    recent = float(base['recent_ppg'])
    n = len(prior)
    w = 0.35 * min(1.0, n / 5)
    form = (1 - w) * season + w * recent
    opportunity = base.get('opportunity') or {}
    opp = opportunity.get('estimated_points')
    if opp is None:
        opp = form
    return {
        'production': _clip(base['projected_points']),
        'd3_candidate': candidate_projection(prior, scoring, base),
        'no_matchup': _clip(baseline_unadjusted),
        'recent_only': _clip(recent * multiplier),
        'season_only': _clip(season * multiplier),
        'opportunity_35': _clip((.65 * form + .35 * float(opp)) * multiplier),
        'opportunity_65': _clip((.35 * form + .65 * float(opp)) * multiplier),
    }

def evaluate_ablation(conn, years, scoring, projection_fn, limit=1000, min_prior=3):
    if scoring not in ('ppr', 'half', 'standard'):
        raise ValueError('Unsupported scoring')
    if not years or len(years)>4 or len(set(years))!=len(years) or any(y<2000 or y>2100 for y in years):
        raise ValueError('Choose 1–4 distinct seasons')
    if not 100<=limit<=3000:
        raise ValueError('Limit must be 100–3000 per season')
    records=[]; per_season={}; per_position={}
    for year in years:
        samples=[]
        games=conn.execute("SELECT * FROM player_games WHERE season=? AND pos IN ('RB','WR','TE') AND week>=4 ORDER BY week,player LIMIT ?",(year,limit)).fetchall()
        for game in games:
            week=int(game['week']); name=game['player']
            prior=conn.execute('SELECT * FROM player_games WHERE season=? AND player=? AND week<? ORDER BY week DESC',(year,name,week)).fetchall()
            if len(prior)<min_prior: continue
            try:
                base=projection_fn(conn,name,year,scoring,(game['opponent'] or '').upper(),before_week=week)
                predicted=_predictions(prior,base,scoring)
            except (ValueError,TypeError,KeyError,ZeroDivisionError):
                continue
            sample={'season':year,'week':week,'position':game['pos'],'actual':_fantasy(game,scoring),'predicted':predicted}
            samples.append(sample)
        records.extend(samples)
        per_season[str(year)]=_metrics(samples)
    for pos in ('RB','WR','TE'):
        per_position[pos]=_metrics([r for r in records if r['position']==pos])
    all_metrics=_metrics(records)
    ranked=sorted(({'recipe':key,**value} for key,value in all_metrics['recipes'].items()),key=lambda x:x['mae'] if x['mae'] is not None else float('inf'))
    return {'version':VERSION,'scoring':scoring,'seasons':years,'scan_limit_per_season':limit,
            'summary':all_metrics,'by_season':per_season,'by_position':per_position,
            'ranked_recipes':ranked,'production_model_unchanged':True,
            'promotion_recommendation':'no_automatic_promotion',
            'methodology':'Each game is predicted using only prior games from the same season; all recipes share identical eligible player-games. Predefined component ablations isolate recency, opportunity blend, and matchup effects. Lower MAE is better.',
            'limitations':['Exploratory ablations, not trained models or a season-held-out model selection procedure',
                           'Season selection and recipe inspection may introduce human selection bias',
                           'Input scan limit truncates the set of eligible games; raise limit for broader coverage',
                           'Only active RB/WR/TE games with >=3 prior recorded games; absences are not evaluated',
                           'No verified snaps, routes, carries, injuries, coverage schemes or weather data',
                           'No calibrated win probabilities or automatic promotion']}

def _metrics(rows):
    if not rows:
        return {'n':0,'recipes':{name:{'mae':None,'bias':None,'delta_vs_production':None} for name in RECIPES}}
    base_mae=mean(abs(r['predicted']['production']-r['actual']) for r in rows)
    data={}
    for recipe in RECIPES:
        mae=mean(abs(r['predicted'][recipe]-r['actual']) for r in rows)
        bias=mean(r['predicted'][recipe]-r['actual'] for r in rows)
        data[recipe]={'mae':round(mae,3),'bias':round(bias,3),'delta_vs_production':round(base_mae-mae,3)}
    return {'n':len(rows),'recipes':data}
