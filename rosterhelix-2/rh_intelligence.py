"""RosterHelix 5.0B research ratings. No schema migration or external dependencies.
Scores are comparative indices, NOT probabilities or validated player valuations.
"""
import math

MODEL='5.0B-research-v1'
POSITIONS=('RB','WR','TE','QB')

def clamp(x,lo,hi):return max(lo,min(hi,x))

def percentile_rank(value, values):
    if not values:return 50.0
    below=sum(x<value for x in values)
    equal=sum(x==value for x in values)
    return round(100*(below+0.5*equal)/len(values),1)

def score_player(proj, positional_pool, remaining_games=None, league_size=12):
    """Scores computed from the existing model; never invent advanced inputs."""
    expected=float(proj['projected_points'])
    floor=float(proj['floor']);ceiling=float(proj['ceiling'])
    sample=int(proj['games'])
    rank=percentile_rank(expected,positional_pool)
    # Reliability is a small adjustment, not a pretend injury model.
    reliability=clamp((sample-3)*0.35,0,3)
    weekly=round(clamp(rank+reliability,0,100),1)
    # ROS value uses expected games and conservative replacement-level contribution.
    # Without a verified schedule, do not manufacture remaining games.
    ros=None
    if remaining_games is not None:
        games=int(remaining_games)
        # Positional pool baseline is a *descriptive* 40th percentile, not a roster optimizer.
        sorted_pool=sorted(positional_pool)
        idx=int((len(sorted_pool)-1)*0.40) if sorted_pool else 0
        replacement=sorted_pool[idx] if sorted_pool else 0
        above=max(0,expected-replacement)
        # Relative to peers at the same position; this rating is not additive across players.
        ros=round(clamp(rank+min(6,games)*0.25+reliability,0,100),1)
        ros_data={'rating':ros,'expected_remaining_games':games,'projected_ros_points':round(expected*games,1),
                  'projected_ros_points_above_positional_reference':round(above*games,1),
                  'reference_ppg':round(replacement,2),'league_size':league_size,
                  'limitations':['Not a roster-specific trade value','Reference is a descriptive within-position percentile, not league replacement level','No injury, depth chart, playoff schedule weighting or roster-slot optimizer']}
    else:
        ros_data={'rating':None,'status':'schedule_unavailable','limitations':['No verified remaining schedule available; ROS rating withheld']}
    return {'name':proj['name'],'team':proj['team'],'position':proj['position'],
            'weekly':{'rating':weekly,'projected_points':expected,'historical_floor':floor,'historical_ceiling':ceiling,
                      'opponent':proj.get('opponent'),'opponent_multiplier':proj.get('opponent_multiplier'),
                      'sample_games':sample,'position_percentile':rank,
                      'limitations':['Rating is relative to the current imported position pool, not a probability',
                                     'Historical floor/ceiling are not calibrated predictive intervals']},
            'trade':ros_data,
            'explanation':{'recent_ppg':proj['recent_ppg'],'season_ppg':proj['season_ppg'],
                           'opportunity':proj.get('opportunity'),'opponent_sample_weeks':proj.get('opponent_sample_weeks')},
            'model_version':MODEL}

def compare_weekly(players):
    if len(players)!=2:return None
    a,b=players
    edge=round(a['weekly']['projected_points']-b['weekly']['projected_points'],2)
    return {'preferred_start':a['name'] if edge>0 else b['name'] if edge<0 else None,
            'projected_edge_a_minus_b':edge,
            'note':'Higher projected points; no calibrated win probability is claimed'}
