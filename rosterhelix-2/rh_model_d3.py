"""5.0D.3 shadow forecasting research; no production model replacement.
All observations are strictly before the evaluation week. No external feeds.
"""
from collections import defaultdict
from statistics import mean
import math

VERSION='5.0D.3-shadow-v1'


def candidate_projection(prior, scoring, baseline_projection):
    """Position-aware robust opportunity shrinkage, with bounded trend and matchup.
    prior: newest first, strictly earlier games. Uses only stored box-score fields.
    """
    pos=prior[0]['pos']; n=len(prior)
    fp=[_fantasy(r,scoring) for r in prior]
    full=mean(fp)
    rec=mean(fp[:min(4,n)])
    # Smooth recent trend toward full-season production for short samples.
    rec_weight={'RB':.30,'WR':.24,'TE':.22}.get(pos,.20)*min(1.,n/7)
    form=full*(1-rec_weight)+rec*rec_weight
    weights=[.88**i for i in range(n)]; sw=sum(weights)
    def weighted(k):return sum(float(r[k] or 0)*w for r,w in zip(prior,weights))/sw
    def total(k):return sum(float(r[k] or 0) for r in prior)
    targets=weighted('targets')
    t=total('targets'); catches=total('receptions'); yards=total('receiving_yards')
    catch=(catches+4)/(t+7) if t else 0
    catch=max(0,min(1,catch))
    ypc=(yards+40)/(catches+5) if catches else 0
    rec_td_rate=(total('receiving_tds')+.35)/(t+35) if t else 0
    rush_td_rate=(total('rushing_tds')+.25)/(n+10)
    receptions=targets*catch
    reception_bonus={'ppr':1.,'half':.5,'standard':0.}[scoring]
    opp=(receptions*ypc/10 + receptions*reception_bonus + targets*rec_td_rate*6 +
         weighted('rushing_yards')/10 + rush_td_rate*6 - weighted('fumbles_lost')*2)
    # Opportunity model has no rush attempts, snap counts or routes; cap its influence.
    weight={'RB':.25,'WR':.42,'TE':.38}.get(pos,0.)*min(1.,n/6)
    estimate=form*(1-weight)+max(0,opp)*weight
    # Retain pregame opponent multiplier from existing projection; shrink to avoid
    # overinterpreting sparse defensive observations. No future-week information.
    multiplier=float(baseline_projection.get('opponent_multiplier') or 1.)
    multiplier=1+(multiplier-1)*.70
    return round(max(0,estimate*multiplier),2)


def _fantasy(row,scoring):
    def v(k):return float(row[k] or 0)
    return (v('passing_yards')/25+v('passing_tds')*4-v('interceptions')*2+
            v('rushing_yards')/10+v('rushing_tds')*6+v('receiving_yards')/10+
            v('receiving_tds')*6+v('receptions')*{'ppr':1,'half':.5,'standard':0}[scoring]-
            v('fumbles_lost')*2)


def evaluate(c,season,scoring,baseline_projection_fn,limit=500,min_prior=3):
    """Walk-forward comparison on identical eligible player-games.
    This is within-season research, not an independent held-out test.
    """
    if scoring not in ('ppr','half','standard'):raise ValueError('Invalid scoring')
    if not 2000<=season<=2100:raise ValueError('Invalid season')
    if not 50<=limit<=1500:raise ValueError('limit must be 50-1500')
    games=c.execute("SELECT * FROM player_games WHERE season=? AND pos IN ('RB','WR','TE') AND week>=? ORDER BY week,player LIMIT ?",(season,min_prior+1,limit)).fetchall()
    result=[];positions=defaultdict(list);weeks=defaultdict(list)
    for g in games:
        week=int(g['week']);name=g['player'];pos=g['pos']
        prior=c.execute('SELECT * FROM player_games WHERE season=? AND player=? AND week<? ORDER BY week DESC',(season,name,week)).fetchall()
        if len(prior)<min_prior:continue
        try:base=baseline_projection_fn(c,name,season,scoring,(g['opponent'] or '').upper(),before_week=week)
        except ValueError:continue
        actual=_fantasy(g,scoring)
        candidate=candidate_projection(prior,scoring,base)
        record={'week':week,'player':name,'position':pos,'actual':round(actual,2),
                'existing':base['projected_points'],'candidate':candidate,
                'season_average':base['season_ppg']}
        result.append(record);positions[pos].append(record);weeks[week].append(record)
    def metrics(items):
        if not items:return {'n':0,'existing_mae':None,'candidate_mae':None,'season_average_mae':None,'candidate_delta_mae':None,'candidate_bias':None}
        a=mean(abs(x['existing']-x['actual']) for x in items)
        b=mean(abs(x['candidate']-x['actual']) for x in items)
        s=mean(abs(x['season_average']-x['actual']) for x in items)
        return {'n':len(items),'existing_mae':round(a,3),'candidate_mae':round(b,3),
                'season_average_mae':round(s,3),'candidate_delta_mae':round(a-b,3),
                'candidate_bias':round(mean(x['candidate']-x['actual'] for x in items),3)}
    overall=metrics(result)
    def pair_accuracy(key):
        good=0;total=0
        for group in weeks.values():
            by_pos=defaultdict(list)
            for item in group:by_pos[item['position']].append(item)
            for same_pos in by_pos.values():
                for i,a in enumerate(same_pos):
                    for b in same_pos[i+1:]:
                        d=a['actual']-b['actual'];pred=a[key]-b[key]
                        if d==0 or pred==0:continue
                        total+=1;good+=int(d*pred>0)
        return {'accuracy':round(good/total,4) if total else None,'comparisons':total}
    return {'version':VERSION,'season':season,'scoring':scoring,'overall':overall,
            'by_position':{p:metrics(v) for p,v in sorted(positions.items())},
            'pairwise':{'existing':pair_accuracy('existing'),'candidate':pair_accuracy('candidate')},
            'eligible_games':len(result),'scan_limit':limit,
            'promotion_recommendation':'candidate_not_promoted',
            'methodology':'For each observed game, only player games and opponent allowances from strictly earlier weeks are used. Both recipes are scored on identical player-games. Candidate uses position-specific recency and opportunity shrinkage; opponent adjustment is dampened. No fitting on evaluation games.',
            'limitations':['Research candidate only; production projections and ratings unchanged',
                'Within-season walk-forward evaluation, not season-held-out or future-week proof',
                'Only active RB/WR/TE games with >=3 prior recorded games; injury absences excluded',
                'No carries, snaps, routes, injury, weather, or coverage scheme inputs in stored table',
                'Scan limit is on input games, so eligible sample may be smaller']}
