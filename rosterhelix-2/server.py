import csv, io, json, os, re, secrets, sqlite3, hashlib, hmac, base64, time, math, threading, datetime
from urllib.request import Request, urlopen
from urllib.error import URLError, HTTPError
from http.server import ThreadingHTTPServer, SimpleHTTPRequestHandler
from pathlib import Path
from urllib.parse import urlparse, parse_qs
from http.cookies import SimpleCookie
from rh_intelligence import score_player,compare_weekly,MODEL,POSITIONS
from rh_model_d3 import evaluate as evaluate_d3
from rh_model_e import evaluate_ablation

ROOT=Path(__file__).resolve().parent
DATA=Path(os.environ.get('ROSTERHELIX_DATA_DIR',str(ROOT/'data')))
DB=DATA/'rosterhelix.sqlite3'
DATA.mkdir(parents=True,exist_ok=True)
MAX_BODY=8*1024*1024
IMPORT_LOCK=threading.Lock()
AUTO_LOG=DATA/"import_status.json"
SCHEDULE_CACHE=DATA/"nfl_schedule_cache.json"
SCHEDULE_LOCK=threading.Lock()
SCHEDULE_SOURCE="https://raw.githubusercontent.com/nflverse/nfldata/master/data/games.csv"
NFLVERSE_URL="https://github.com/nflverse/nflverse-data/releases/download/stats_player/stats_player_week_{season}.csv"
GAME_COLUMNS=["season","week","player","team","pos","opponent","passing_yards","passing_tds","interceptions","rushing_yards","rushing_tds","receptions","receiving_yards","receiving_tds","targets","fumbles_lost"]

def connect():
 c=sqlite3.connect(DB,timeout=15)
 c.row_factory=sqlite3.Row
 c.execute('PRAGMA journal_mode=WAL')
 return c

def setup():
 with connect() as c:
  c.executescript('''CREATE TABLE IF NOT EXISTS users(id INTEGER PRIMARY KEY,email TEXT UNIQUE NOT NULL,password TEXT NOT NULL,created INTEGER NOT NULL);
CREATE TABLE IF NOT EXISTS sessions(token_hash TEXT PRIMARY KEY,user_id INTEGER NOT NULL,csrf TEXT NOT NULL,expires INTEGER NOT NULL);
CREATE TABLE IF NOT EXISTS leagues(id INTEGER PRIMARY KEY,user_id INTEGER NOT NULL,name TEXT NOT NULL,scoring TEXT NOT NULL,roster TEXT NOT NULL DEFAULT '[]');
CREATE TABLE IF NOT EXISTS player_games(id INTEGER PRIMARY KEY,season INTEGER NOT NULL,week INTEGER NOT NULL,player TEXT NOT NULL,team TEXT,pos TEXT,opponent TEXT,passing_yards REAL DEFAULT 0,passing_tds REAL DEFAULT 0,interceptions REAL DEFAULT 0,rushing_yards REAL DEFAULT 0,rushing_tds REAL DEFAULT 0,receptions REAL DEFAULT 0,receiving_yards REAL DEFAULT 0,receiving_tds REAL DEFAULT 0,targets REAL DEFAULT 0,fumbles_lost REAL DEFAULT 0, UNIQUE(season,week,player,team));
CREATE INDEX IF NOT EXISTS idx_pg_player ON player_games(player,season,week);
CREATE INDEX IF NOT EXISTS idx_pg_season_week ON player_games(season,week DESC);
CREATE TABLE IF NOT EXISTS projection_snapshots(id INTEGER PRIMARY KEY,season INTEGER NOT NULL,week INTEGER NOT NULL,player TEXT NOT NULL,team TEXT NOT NULL,opponent TEXT NOT NULL,scoring TEXT NOT NULL,projected REAL NOT NULL,created_utc INTEGER NOT NULL, UNIQUE(season,week,player,team,scoring));
CREATE INDEX IF NOT EXISTS idx_snapshot_season_week ON projection_snapshots(season,week);''')
  cols={r[1] for r in c.execute('PRAGMA table_info(projection_snapshots)')}
  if 'model_version' not in cols:c.execute("ALTER TABLE projection_snapshots ADD COLUMN model_version TEXT NOT NULL DEFAULT '3.5-historical'")

def hash_password(p,salt=None):
 salt=salt or secrets.token_bytes(16)
 digest=hashlib.scrypt(p.encode(),salt=salt,n=16384,r=8,p=1)
 return base64.b64encode(salt+digest).decode()

def verify_password(p,stored):
 try:
  raw=base64.b64decode(stored);return hmac.compare_digest(hashlib.scrypt(p.encode(),salt=raw[:16],n=16384,r=8,p=1),raw[16:])
 except Exception:return False

def fantasy(row,scoring='ppr'):
 d=dict(row);v=lambda k:float(d.get(k) or 0)
 return round(v('passing_yards')/25+v('passing_tds')*4-v('interceptions')*2+v('rushing_yards')/10+v('rushing_tds')*6+v('receiving_yards')/10+v('receiving_tds')*6+v('receptions')*{'standard':0,'half':.5,'ppr':1}.get(scoring,1)-v('fumbles_lost')*2,2)

def nflverse_rows(csv_bytes, season):
 """Normalize older and newer nflverse weekly CSV layouts."""
 reader=csv.DictReader(io.StringIO(csv_bytes.decode('utf-8-sig')))
 fields=set(reader.fieldnames or [])
 candidates={
  'player':('player_name','player_display_name','player'),
  'team':('recent_team','team','posteam'),
  'pos':('position','position_group','pos'),
  'opponent':('opponent_team','opponent','defteam'),
  'interceptions':('passing_interceptions','interceptions'),
  'fumbles_lost':('fumbles_lost',),
 }
 required={'season','week','passing_yards','rushing_yards','receiving_yards','receptions'}
 missing=required-fields
 for field in ('player','team','pos'):
  if not any(x in fields for x in candidates[field]):missing.add(field+' (accepted: '+', '.join(candidates[field])+')')
 if missing:raise ValueError('Unexpected nflverse schema; missing: '+', '.join(sorted(missing)))
 selected={field:next((x for x in names if x in fields),None) for field,names in candidates.items()}
 result=[]
 for row in reader:
  if (row.get('season') or '').strip()!=str(season):continue
  if (row.get('season_type') or 'REG').strip().upper() not in ('REG','REGULAR'):continue
  values=[]
  for col in GAME_COLUMNS:
   key=selected.get(col,col)
   raw=(row.get(key) or '').strip() if key else ''
   if col in ('season','week'):value=int(raw)
   elif col in ('player','team','pos','opponent'):value=raw[:100]
   else:
    value=float(raw or 0)
    if not math.isfinite(value):raise ValueError('Non-finite statistic')
   values.append(value)
  if not values[2] or not values[3] or not 1<=values[1]<=25:continue
  result.append(values)
  if len(result)>50000:raise ValueError('Season exceeds 50,000 player games')
 if not result:raise ValueError('No regular-season player rows found')
 return result

def import_nflverse_season(season):
 url=NFLVERSE_URL.format(season=season)
 request=Request(url,headers={'User-Agent':'RosterHelix-DataManager/1.0','Accept':'text/csv'})
 with urlopen(request,timeout=35) as response:
  data=response.read(20*1024*1024+1)
 if len(data)>20*1024*1024:raise ValueError('Season CSV exceeds 20 MB safety limit')
 rows=nflverse_rows(data,season)
 placeholders=','.join('?' for _ in GAME_COLUMNS)
 updates=','.join(f'{x}=excluded.{x}' for x in GAME_COLUMNS[4:])
 with connect() as c:
  c.executemany('INSERT INTO player_games('+','.join(GAME_COLUMNS)+') VALUES('+placeholders+') ON CONFLICT(season,week,player,team) DO UPDATE SET '+updates,rows)
 return len(rows)



def write_import_status(status, season, count=None, error=None):
 """Record the latest scheduled run on the persistent disk."""
 info={'status':status,'season':season,'timestamp_utc':int(time.time()),'rows_processed':count,'error':error}
 temp=AUTO_LOG.with_suffix('.tmp')
 temp.write_text(json.dumps(info))
 temp.replace(AUTO_LOG)

def current_nfl_season():
 today=time.gmtime()
 return today.tm_year if today.tm_mon>=3 else today.tm_year-1

def season_latest(c):
 return c.execute('SELECT MAX(season) FROM player_games').fetchone()[0]

def player_summary(c,name,season,scoring):
 rows=c.execute('SELECT * FROM player_games WHERE player=? AND season=? ORDER BY week DESC',(name,season)).fetchall()
 if not rows:return None
 r=rows[0]; pts=[fantasy(x,scoring) for x in rows]; recent=pts[:5]
 targets=sum(float(x['targets'] or 0) for x in rows)
 team_targets=c.execute('SELECT COALESCE(SUM(targets),0) FROM player_games WHERE season=? AND team=? AND week IN ('+','.join('?' for _ in rows)+')',(season,r['team'],*[x['week'] for x in rows])).fetchone()[0] if r['team'] else 0
 # Opponent allowance is retrospective: same-season games, same position, excluding this player's games.
 opponents={}
 for x in rows:
  opp=x['opponent']
  if not opp:continue
  matches=c.execute('SELECT * FROM player_games WHERE season=? AND opponent=? AND pos=? AND week=? AND player<>?',(season,opp,x['pos'],x['week'],name)).fetchall()
  if matches:opponents[opp]=round(sum(fantasy(m,scoring) for m in matches)/len(matches),1)
 return {'name':name,'team':r['team'],'position':r['pos'],'season':season,'games':len(rows),'ppg':round(sum(pts)/len(pts),2),'recent_ppg':round(sum(recent)/len(recent),2),'last_five':list(reversed(recent)),'targets_per_game':round(targets/len(rows),2),'receptions_per_game':round(sum(x['receptions'] or 0 for x in rows)/len(rows),2),'target_share_proxy':round(targets/team_targets*100,1) if team_targets else None,'historical_opponent_allowed':opponents,'last_opponent':r['opponent']}

def comparison(c,names,season,scoring,kind):
 if not isinstance(names,list) or len(names)<2 or len(names)>12 or any(not isinstance(x,str) or len(x)>100 for x in names):raise ValueError('Select two or more valid players')
 summaries=[player_summary(c,n,season,scoring) for n in names]
 if any(x is None for x in summaries):raise ValueError('One or more players were not found for this season')
 return {'type':kind,'season':season,'scoring':scoring,'players':summaries,'limitations':['Historical performance only; not a validated weekly projection','No live injury, snap percentage, coverage scheme, or upcoming matchup feed connected','Target share is an approximation using recorded team player targets; missing records affect it']}


def percentile(values, fraction):
 """Linear-interpolated empirical percentile; descriptive, not a calibrated forecast interval."""
 values=sorted(values)
 if not values:return 0.0
 index=(len(values)-1)*fraction;lo=int(index);hi=min(lo+1,len(values)-1)
 return values[lo]+(values[hi]-values[lo])*(index-lo)

def opportunity_projection(rows, scoring):
 """Estimate opportunity and efficiency separately using recorded box-score columns only.
 Returns None for QB or insufficient samples. All rates use additive shrinkage.
 """
 if len(rows)<3 or rows[0]['pos'] not in ('RB','WR','TE'):return None
 pos=rows[0]['pos'];n=len(rows)
 # Chronological recent emphasis; all observed games contribute.
 weights=[0.85**i for i in range(n)]
 def mean(field):
  return sum(float(r[field] or 0)*w for r,w in zip(rows,weights))/sum(weights)
 def total(field):return sum(float(r[field] or 0) for r in rows)
 targets=mean('targets');carries=mean('carries') if 'carries' in rows[0].keys() else 0
 # nflverse player_games currently has no carries column. Avoid pretending it does.
 # RB rushing opportunity uses yards per game as a descriptive proxy, not carries.
 receptions=total('receptions');target_total=total('targets')
 catch_rate=(receptions+3.0)/(target_total+5.0) if target_total>0 else 0
 catch_rate=max(0,min(1,catch_rate))
 receiving_yards=total('receiving_yards');yards_per_catch=(receiving_yards+35)/(receptions+4) if receptions else 0
 exp_receptions=targets*catch_rate
 exp_rec_yards=exp_receptions*yards_per_catch
 # TD rates are heavily shrunk to prevent 1-2 touchdowns from dominating a forecast.
 rec_tds=(total('receiving_tds')+0.3)/(target_total+25) if target_total else 0
 exp_rec_tds=targets*rec_tds
 rush_yards=mean('rushing_yards')
 rush_tds=(total('rushing_tds')+0.3)/(n+8)
 exp_rush_tds=rush_tds
 fumbles=mean('fumbles_lost')
 ppr={'ppr':1,'half':0.5,'standard':0}[scoring]
 estimate=exp_rec_yards/10+exp_receptions*ppr+exp_rec_tds*6+rush_yards/10+exp_rush_tds*6-fumbles*2
 return {'estimated_points':round(max(0,estimate),2),'targets_per_game':round(targets,2),
  'expected_receptions':round(exp_receptions,2),'expected_receiving_yards':round(exp_rec_yards,1),
  'expected_receiving_tds':round(exp_rec_tds,3),'expected_rushing_yards':round(rush_yards,1),
  'expected_rushing_tds':round(exp_rush_tds,3),'catch_rate_estimate':round(catch_rate,3),
  'rush_attempts_available':False,'snap_share_available':False,'routes_run_available':False,
  'methodology':'Exponential recent weighting (0.85 per older game) for targets and rushing yards. Catch rate, yards per reception and touchdown rates use additive shrinkage. No carries, snaps, routes, red-zone attempts, injuries or coverage scheme columns are present in the imported game logs.'}

def player_projection(c,name,season,scoring,opponent='',before_week=None):
 """Transparent baseline using historical game logs and optional defensive positional allowance."""
 rows=c.execute('SELECT * FROM player_games WHERE player=? AND season=? AND (? IS NULL OR week<?) ORDER BY week DESC',(name,season,before_week,before_week)).fetchall()
 if not rows:raise ValueError('Player not found for the selected season')
 pos=rows[0]['pos'];points=[fantasy(r,scoring) for r in rows]
 n=len(points);recent=points[:min(5,n)];season_avg=sum(points)/n;recent_avg=sum(recent)/len(recent)
 # Blend recent form with full-season mean; small samples shrink toward season mean.
 recent_weight=.35*min(1,n/5)
 baseline=(1-recent_weight)*season_avg+recent_weight*recent_avg
 multiplier=1.0;sample_weeks=0;allowance=None;league_allowance=None
 if opponent:
  if pos not in ('QB','RB','WR','TE'):raise ValueError('Opponent adjustment unavailable for this position')
  defense_rows=c.execute("SELECT week,opponent,pos,passing_yards,passing_tds,interceptions,rushing_yards,rushing_tds,receptions,receiving_yards,receiving_tds,fumbles_lost FROM player_games WHERE season=? AND pos=? AND opponent IS NOT NULL AND opponent<>'' AND (? IS NULL OR week<?)",(season,pos,before_week,before_week)).fetchall()
  per_defense={};all_weekly={}
  for r in defense_rows:
   key=(r['opponent'].upper(),r['week']);per_defense[key]=per_defense.get(key,0)+fantasy(r,scoring)
  for (team,week),pts in per_defense.items():all_weekly.setdefault(team,[]).append(pts)
  observed=all_weekly.get(opponent.upper(),[])
  # Compare weekly positional team totals against league average of the same metric.
  if observed and per_defense:
   sample_weeks=len(observed);allowance=sum(observed)/sample_weeks
   league_allowance=sum(per_defense.values())/len(per_defense)
   if league_allowance>0:
    raw=allowance/league_allowance
    shrink=sample_weeks/(sample_weeks+8)
    multiplier=max(.85,min(1.15,1+(raw-1)*.35*shrink))
 opportunity=opportunity_projection(rows,scoring)
 # A cautious 50/50 blend; a separate opportunity model is not yet proven superior.
 blended=.5*baseline+.5*opportunity['estimated_points'] if opportunity else baseline
 projection=round(max(0,blended*multiplier),2)
 # Empirical distribution shifted by the baseline and opponent adjustment; not calibrated probabilities.
 shift=projection-season_avg
 floor=round(max(0,percentile(points,.20)+shift),2)
 ceiling=round(max(projection,percentile(points,.80)+shift),2)
 floor=min(floor,projection)
 return {'name':name,'team':rows[0]['team'],'position':pos,'season':season,'scoring':scoring,'opponent':opponent or None,
  'projected_points':projection,'floor':floor,'ceiling':ceiling,'games':n,'opportunity':opportunity,'model_version':'3.6-opportunity-v1' if before_week is None else '4.4-walk-forward-candidate',
  'season_ppg':round(season_avg,2),'recent_ppg':round(recent_avg,2),
  'opponent_multiplier':round(multiplier,3),'opponent_sample_weeks':sample_weeks,
  'opponent_position_points_allowed':round(allowance,2) if allowance is not None else None,
  'league_position_points_allowed':round(league_allowance,2) if league_allowance is not None else None,
  'confidence':'low' if n<4 else 'moderate' if n<8 else 'historical sample adequate',
  'methodology':'For RB/WR/TE with 3+ games, 50% historical fantasy baseline and 50% box-score opportunity estimate; otherwise 3.5 historical baseline. Opponent multiplier uses league-relative position points allowed, shrunk and capped at +/-15%. Historical 20th/80th percentile ranges are not calibrated probability intervals.',
  'limitations':['Schedule auto-detection is available separately; manual opponent choices are not verified','No live injury, depth chart, snap share, routes run, carries, weather or coverage scheme data','The 3.6 blend has not been shown to outperform 3.5 on held-out games; historical intervals are not calibrated']}


def walk_forward_backtest(c,season,scoring,min_prior=3,max_rows=1800):
 """True pregame evaluation: every forecast uses only weeks strictly before the target.

 This tests the current 3.6 recipe as a candidate, not a new fitted model.
 Results include only players with prior game logs and an actual game that week.
 """
 if scoring not in ('ppr','half','standard'):raise ValueError('Invalid scoring')
 if not 1999<=season<=2100:raise ValueError('Invalid season')
 games=c.execute("SELECT * FROM player_games WHERE season=? AND pos IN ('RB','WR','TE') AND week>=? ORDER BY week,player LIMIT ?",(season,min_prior+1,max_rows)).fetchall()
 if not games:return {'season':season,'scoring':scoring,'evaluated':0,'notice':'Not enough historical data to backtest'}
 evaluated=[];weekly={};by_position={};pair_week={}
 for game in games:
  week=int(game['week']);name=game['player'];pos=game['pos']
  try:
   projection=player_projection(c,name,season,scoring,(game['opponent'] or '').upper(),before_week=week)
  except ValueError:continue
  if projection['games']<min_prior:continue
  actual=fantasy(game,scoring);prediction=projection['projected_points']
  baseline=projection['season_ppg']
  item={'week':week,'player':name,'position':pos,'predicted':prediction,'baseline':baseline,'actual':actual,'error':round(prediction-actual,2),'baseline_error':round(baseline-actual,2),'in_historical_range':projection['floor']<=actual<=projection['ceiling']}
  evaluated.append(item);weekly.setdefault(week,[]).append(item);by_position.setdefault(pos,[]).append(item);pair_week.setdefault((week,pos),[]).append(item)
 def stats(rows):
  n=len(rows)
  return {'n':n,'model_mae':round(sum(abs(x['error']) for x in rows)/n,3) if n else None,'season_average_mae':round(sum(abs(x['baseline_error']) for x in rows)/n,3) if n else None,'model_bias':round(sum(x['error'] for x in rows)/n,3) if n else None,'historical_range_coverage':round(sum(x['in_historical_range'] for x in rows)/n,3) if n else None}
 decisions=[]
 # For every same-week same-position pair, compare forecast and actual ranking.
 # Ties in predictions or outcomes are excluded; this is NOT lineup-level win rate.
 for key,rows in pair_week.items():
  ordered=sorted(rows,key=lambda r:r['player'])
  for i,a in enumerate(ordered):
   for b in ordered[i+1:]:
    if a['predicted']==b['predicted'] or a['actual']==b['actual']:continue
    decisions.append((a['predicted']-b['predicted'])*(a['actual']-b['actual'])>0)
 return {'version':'4.4-walk-forward-evaluation','season':season,'scoring':scoring,'evaluated':len(evaluated),'overall':stats(evaluated),'by_position':{k:stats(v) for k,v in sorted(by_position.items())},'by_week':[{**{'week':w},**stats(rows)} for w,rows in sorted(weekly.items())], 'pairwise_rank_accuracy':round(sum(decisions)/len(decisions),3) if decisions else None,'pairwise_comparisons':len(decisions),'sample':evaluated[-30:], 'methodology':'Each prediction uses only games with week strictly earlier than the evaluated game; defensive opponent allowances are also restricted to earlier weeks. Same-season season-average baseline is computed using prior weeks only. Evaluates existing 3.6 recipe without fitting parameters on test weeks.','limitations':['Only RB/WR/TE with at least three prior logged games and a recorded game are evaluated; missed/inactive games are excluded','This is within-season walk-forward testing, not independent season-held-out validation','Pairwise ranking evaluates all eligible same-week same-position pairs, not actual fantasy lineups','Floor/ceiling are uncalibrated historical ranges; coverage is diagnostic only','No live snap, route, injury, coverage or weather feeds are used','The limit of 1800 player-games bounds endpoint runtime; larger seasons may be truncated']}


# 3.5: schedule rows are sourced from nflverse's nflverse/nfldata games CSV.
# Only regular-season scheduled matchups are used; no fabricated opponent fallback.
def fetch_schedule(force=False):
 with SCHEDULE_LOCK:
  if not force and SCHEDULE_CACHE.exists():
   try:
    saved=json.loads(SCHEDULE_CACHE.read_text())
    if time.time()-saved['fetched_utc']<6*3600 and saved.get('games'):return saved
   except (ValueError,KeyError,OSError,TypeError):pass
  try:
   req=Request(SCHEDULE_SOURCE,headers={'User-Agent':'RosterHelix/3.5','Accept':'text/csv'})
   with urlopen(req,timeout=15) as resp: raw=resp.read(6*1024*1024+1)
   if len(raw)>6*1024*1024:raise ValueError('Schedule too large')
   reader=csv.DictReader(io.StringIO(raw.decode('utf-8-sig')))
   required={'season','week','home_team','away_team','gameday'}
   if not required.issubset(set(reader.fieldnames or [])):raise ValueError('Schedule schema changed')
   games=[]
   for row in reader:
    if (row.get('game_type') or row.get('season_type') or 'REG').upper() not in ('REG','REGULAR'):continue
    try:
     season=int(row['season']);week=int(row['week']);date=row['gameday'][:10]
     datetime.date.fromisoformat(date)
     home=row['home_team'].strip().upper();away=row['away_team'].strip().upper()
     if not (1999<=season<=2100 and 1<=week<=18 and re.fullmatch('[A-Z]{2,3}',home) and re.fullmatch('[A-Z]{2,3}',away)):continue
     # Time is not used to imply kickoff time: gameday date is the available guarantee.
     games.append({'season':season,'week':week,'date':date,'home':home,'away':away})
    except (ValueError,KeyError,TypeError):continue
   if not games:raise ValueError('No valid schedule rows')
   saved={'fetched_utc':int(time.time()),'source':SCHEDULE_SOURCE,'games':games}
   temp=SCHEDULE_CACHE.with_suffix('.tmp');temp.write_text(json.dumps(saved));temp.replace(SCHEDULE_CACHE)
   return saved
  except Exception:
   if SCHEDULE_CACHE.exists():
    try:
     saved=json.loads(SCHEDULE_CACHE.read_text())
     if saved.get('games'):
      saved['stale']=True;return saved
    except (ValueError,OSError):pass
   raise

def schedule_matchup(games,season,team,week=None):
 if not team:return None
 today=datetime.datetime.now(datetime.timezone.utc).date()
 choices=sorted((g for g in games if g['season']==season and team in (g['home'],g['away']) and (week is None or g['week']==week) and g['date']>=today.isoformat()),key=lambda g:(g['date'],g['week']))
 if not choices:return None
 g=choices[0]
 return {'week':g['week'],'date':g['date'],'opponent':g['away'] if team==g['home'] else g['home'],'location':'home' if team==g['home'] else 'away'}

def save_upcoming_snapshots():
 """Immutable, pre-game forecasts. Called only after successful secured daily import."""
 try:schedule=fetch_schedule()
 except Exception:return {'saved':0,'reason':'Schedule unavailable'}
 today=datetime.datetime.now(datetime.timezone.utc).date()
 with connect() as c:
  season=current_nfl_season()
  future=sorted((g for g in schedule['games'] if g['season']==season and g['date']>today.isoformat()),key=lambda g:(g['date'],g['week']))
  if not future:return {'saved':0,'reason':'No future regular-season games'}
  week=future[0]['week']
  games=[g for g in future if g['week']==week]
  # Only teams scheduled for the same future week; avoid projections for BYE teams.
  opponents={g['home']:g['away'] for g in games}
  opponents.update({g['away']:g['home'] for g in games})
  rows=c.execute("SELECT player,team,MAX(week) latest FROM player_games WHERE season=? AND pos IN ('QB','RB','WR','TE') GROUP BY player,team",(season,)).fetchall()
  now=int(time.time());saved=0
  for r in rows:
   team=(r['team'] or '').upper();opp=opponents.get(team)
   if not opp or r['latest']>=week:continue
   for scoring in ('ppr','half','standard'):
    try:estimate=player_projection(c,r['player'],season,scoring,opp)
    except ValueError:continue
    result=c.execute('INSERT OR IGNORE INTO projection_snapshots(season,week,player,team,opponent,scoring,projected,created_utc,model_version) VALUES(?,?,?,?,?,?,?,?,?)',(season,week,r['player'],team,opp,scoring,estimate['projected_points'],now,'3.6-opportunity-v1'))
    saved+=result.rowcount
  return {'saved':saved,'season':season,'week':week,'schedule_stale':bool(schedule.get('stale'))}

def accuracy_report(c,season,scoring):
 # Compare only snapshots against matching completed game logs; never invent missing outcomes.
 rows=c.execute("""SELECT s.week,s.player,s.team,s.opponent,s.projected,s.created_utc,s.model_version,p.* FROM projection_snapshots s JOIN player_games p ON p.season=s.season AND p.week=s.week AND p.player=s.player AND p.team=s.team WHERE s.season=? AND s.scoring=? ORDER BY s.week DESC,s.player LIMIT 10000""",(season,scoring)).fetchall()
 data=[]
 for r in rows:
  actual=fantasy(r,scoring);error=r['projected']-actual
  data.append({'week':r['week'],'player':r['player'],'team':r['team'],'projected':r['projected'],'actual':actual,'error':round(error,2),'abs_error':round(abs(error),2),'model_version':r['model_version']})
 n=len(data)
 by_week={}
 for d in data:by_week.setdefault(d['week'],[]).append(d)
 weekly=[{'week':w,'count':len(v),'mae':round(sum(x['abs_error'] for x in v)/len(v),2),'bias':round(sum(x['error'] for x in v)/len(v),2)} for w,v in sorted(by_week.items())]
 versions=sorted(set(d['model_version'] for d in data))
 return {'season':season,'scoring':scoring,'model_versions':versions,'evaluated':n,'mae':round(sum(d['abs_error'] for d in data)/n,2) if n else None,'bias':round(sum(d['error'] for d in data)/n,2) if n else None,'weekly':weekly,'recent':data[:30],'methodology':'Pre-game immutable version-labeled projection snapshots compared to imported actual game logs. MAE = average absolute error; bias = average projected minus actual. Only matched records are evaluated.','limitations':['No snapshots exist for games before 3.5 was enabled','Missing game logs and inactive players are not counted as zero; results have selection bias','A low MAE alone does not establish start/sit decision quality or a calibrated probability']}

class Handler(SimpleHTTPRequestHandler):
 def __init__(self,*a,**kw):super().__init__(*a,directory=str(ROOT/'static'),**kw)
 def send_json(self,obj,status=200,headers=None):
  b=json.dumps(obj).encode();self.send_response(status);self.send_header('Content-Type','application/json; charset=utf-8');self.send_header('Content-Length',str(len(b)));self.send_header('Cache-Control','no-store');self.send_header('X-Content-Type-Options','nosniff')
  for k,v in (headers or {}).items():self.send_header(k,v)
  self.end_headers();self.wfile.write(b)
 def cookie(self):
  c=SimpleCookie()
  try:c.load(self.headers.get('Cookie',''));return c['rh2_session'].value if 'rh2_session' in c else ''
  except Exception:return ''
 def user(self):
  token=self.cookie()
  if not token:return None
  with connect() as c:return c.execute('SELECT u.id,u.email,s.csrf FROM sessions s JOIN users u ON u.id=s.user_id WHERE s.token_hash=? AND s.expires>?',(hashlib.sha256(token.encode()).hexdigest(),int(time.time()))).fetchone()
 def csrf(self,u):return bool(u and hmac.compare_digest(self.headers.get('X-CSRF-Token',''),u['csrf']))
 def admin(self,u):return bool(u and os.getenv('ADMIN_EMAIL') and u['email']==os.getenv('ADMIN_EMAIL','').strip().lower())
 def origin_ok(self):
  origin=self.headers.get('Origin','');host=self.headers.get('Host','')
  return bool(origin and urlparse(origin).netloc.lower()==host.lower() and urlparse(origin).scheme in ('http','https'))
 def read_body(self):
  try:n=int(self.headers.get('Content-Length','0'))
  except ValueError:raise ValueError('Invalid request size')
  if n<0 or n>MAX_BODY:raise ValueError('Request too large')
  return self.rfile.read(n)
 def do_GET(self):
  p=urlparse(self.path).path
  if p=='/api/health':return self.send_json({'ok':True,'version':'3.6-player-intelligence','current_nfl_season':current_nfl_season()})
  if p=='/api/automation/status':
   # Public status intentionally exposes no credentials or internal error details.
   try:
    info=json.loads(AUTO_LOG.read_text())
    return self.send_json({k:info.get(k) for k in ('status','season','timestamp_utc','rows_processed')})
   except (FileNotFoundError,ValueError,OSError):return self.send_json({'status':'never_run'})
  if p=='/api/auth/me':
   u=self.user();return self.send_json({'authenticated':bool(u),'email':u['email'] if u else None,'csrf':u['csrf'] if u else None,'admin':self.admin(u)})
  if p=='/api/stats':
   with connect() as c:
    count=c.execute('SELECT count(*) n,count(DISTINCT player) players,min(season) first,max(season) last FROM player_games').fetchone()
   return self.send_json({'games':count['n'],'players':count['players'],'first_season':count['first'],'last_season':count['last'],'demo':count['n']==0,'current_nfl_season':current_nfl_season()})
  if p=='/api/search':
   q=parse_qs(urlparse(self.path).query);term=q.get('q',[''])[0].strip()[:80];season=q.get('season',[''])[0]
   with connect() as c:
    year=int(season) if season.isdigit() else season_latest(c)
    if year is None:return self.send_json({'season':None,'players':[]})
    rows=c.execute('SELECT player,MAX(pos) pos,MAX(team) team,COUNT(*) games FROM player_games WHERE season=? AND player LIKE ? GROUP BY player ORDER BY CASE WHEN player LIKE ? THEN 0 ELSE 1 END, games DESC,player LIMIT 75',(year,'%'+term+'%',term+'%')).fetchall()
   return self.send_json({'season':year,'players':[dict(r) for r in rows]})
  if p=='/api/analyze':
   q=parse_qs(urlparse(self.path).query);kind=q.get('type',['start'])[0];scoring=q.get('scoring',['ppr'])[0]
   if kind not in ('start','trade') or scoring not in ('ppr','half','standard'):return self.send_json({'error':'Invalid comparison options'},400)
   names=q.get('player',[]);season=q.get('season',[''])[0]
   try:
    with connect() as c:
     year=int(season) if season.isdigit() else season_latest(c)
     if year is None:return self.send_json({'error':'Import a season first'},400)
     result=comparison(c,names,year,scoring,kind)
    return self.send_json(result)
   except ValueError as e:return self.send_json({'error':str(e)},400)
  if p=='/api/schedule':
   q=parse_qs(urlparse(self.path).query);season=q.get('season',[''])[0]
   try:
    year=int(season) if season.isdigit() else current_nfl_season()
    saved=fetch_schedule()
    teams=q.get('team',[])
    if len(teams)>2 or any(not re.fullmatch('[A-Z]{2,3}',t.upper()) for t in teams):return self.send_json({'error':'Invalid team'},400)
    result={t.upper():schedule_matchup(saved['games'],year,t.upper()) for t in teams}
    return self.send_json({'season':year,'matchups':result,'source':saved['source'],'fetched_utc':saved['fetched_utc'],'stale':bool(saved.get('stale')),'notice':'Schedule dates, not kickoff times. No future matchup means bye, season ended, or schedule unavailable.'})
   except (OSError,ValueError,URLError,HTTPError,TimeoutError) as e:return self.send_json({'error':'Verified schedule unavailable; choose opponents manually','detail':type(e).__name__},503)
  if p=='/api/accuracy':
   q=parse_qs(urlparse(self.path).query);scoring=q.get('scoring',['ppr'])[0];season=q.get('season',[''])[0]
   if scoring not in ('ppr','half','standard'):return self.send_json({'error':'Invalid scoring'},400)
   with connect() as c:
    year=int(season) if season.isdigit() else current_nfl_season()
    return self.send_json(accuracy_report(c,year,scoring))
  if p=='/api/backtest':
   q=parse_qs(urlparse(self.path).query);season=q.get('season',[''])[0];scoring=q.get('scoring',['ppr'])[0]
   if scoring not in ('ppr','half','standard'):return self.send_json({'error':'Invalid scoring'},400)
   try:
    with connect() as c:
     year=int(season) if season.isdigit() else season_latest(c)
     if year is None:return self.send_json({'error':'Import player data first'},400)
     result=walk_forward_backtest(c,year,scoring)
    return self.send_json(result)
   except ValueError as e:return self.send_json({'error':str(e)},400)
  if p=='/api/intelligence/research/ablation':
   q=parse_qs(urlparse(self.path).query)
   raw=q.get('seasons',['2023,2024,2025'])[0]
   scoring=q.get('scoring',['ppr'])[0]
   limit=q.get('limit',['600'])[0]
   try:
    years=[int(v.strip()) for v in raw.split(',')]
    if not years or len(years)>4 or len(set(years))!=len(years) or any(y<2000 or y>current_nfl_season() for y in years):raise ValueError('Choose 1–4 distinct valid seasons')
    if not limit.isdigit() or not 100<=int(limit)<=3000:raise ValueError('Limit must be 100–3000')
    with connect() as c:
     report=evaluate_ablation(c,years,scoring,player_projection,int(limit))
    return self.send_json(report)
   except ValueError as e:return self.send_json({'error':str(e)},400)
  if p=='/api/intelligence/model-lab/multiseason':
   q=parse_qs(urlparse(self.path).query)
   raw=q.get('seasons',['2023,2024,2025'])[0]
   scoring=q.get('scoring',['ppr'])[0]
   limit=q.get('limit',['300'])[0]
   try:
    years=[int(v.strip()) for v in raw.split(',')]
    if not 1<=len(years)<=4 or len(set(years))!=len(years) or any(not 2000<=v<=current_nfl_season() for v in years):raise ValueError('Choose 1-4 distinct valid seasons')
    if scoring not in ('ppr','half','standard') or not limit.isdigit() or not 50<=int(limit)<=1000:raise ValueError('Invalid scoring or limit (50-1000)')
    with connect() as c:
     reports=[evaluate_d3(c,year,scoring,player_projection,int(limit)) for year in years]
    valid=[r for r in reports if r['overall']['n']]
    n=sum(r['overall']['n'] for r in valid)
    def weighted(key):return round(sum(r['overall'][key]*r['overall']['n'] for r in valid)/n,3) if n else None
    summary={'player_games':n,'existing_mae':weighted('existing_mae'),'candidate_mae':weighted('candidate_mae'),'season_average_mae':weighted('season_average_mae')}
    summary['candidate_delta_mae']=round(summary['existing_mae']-summary['candidate_mae'],3) if n else None
    return self.send_json({'version':'5.0D.4-multiseason-research','scoring':scoring,'summary':summary,'seasons':reports,'production_model_unchanged':True,'limitations':['Up to four seasons, each independently walk-forward evaluated','Per-season input scan limit may produce fewer eligible games','Cross-season aggregate is player-game weighted; seasons are not held out from human model-design decisions','No automatic model promotion or claims of verified accuracy']})
   except ValueError as e:return self.send_json({'error':str(e)},400)
  if p=='/api/intelligence/model-lab':
   q=parse_qs(urlparse(self.path).query)
   season=q.get('season',[''])[0];scoring=q.get('scoring',['ppr'])[0];limit=q.get('limit',['500'])[0]
   if scoring not in ('ppr','half','standard') or (season and (not season.isdigit() or not 2000<=int(season)<=current_nfl_season())) or not limit.isdigit() or not 50<=int(limit)<=1500:
    return self.send_json({'error':'Invalid season, scoring or limit'},400)
   try:
    with connect() as c:
     year=int(season) if season else season_latest(c)
     if year is None:return self.send_json({'error':'Import player data first'},400)
     report=evaluate_d3(c,year,scoring,player_projection,int(limit))
    return self.send_json(report)
   except ValueError as e:return self.send_json({'error':str(e)},400)
  if p=='/api/intelligence/validation':
   q=parse_qs(urlparse(self.path).query)
   season=q.get('season',[''])[0];scoring=q.get('scoring',['ppr'])[0]
   if scoring not in ('ppr','half','standard') or (season and (not season.isdigit() or not 2000<=int(season)<=current_nfl_season())):
    return self.send_json({'error':'Invalid season or scoring'},400)
   try:
    with connect() as c:
     year=int(season) if season else season_latest(c)
     if year is None:return self.send_json({'error':'Import player data first'},400)
     report=walk_forward_backtest(c,year,scoring)
    model=(report.get('overall') or {}).get('model_mae')
    baseline=(report.get('overall') or {}).get('season_average_mae')
    gain=round(baseline-model,3) if model is not None and baseline is not None else None
    report['mae_improvement']=gain
    report['release_gate']={'passed':gain is not None and gain>0,
     'summary':('Current formula beats the historical baseline on this evaluated sample; not proof of generalization.' if gain is not None and gain>0 else 'Current formula has not beaten the historical baseline on this sample. Do not promote a new formula.'),
     'status':'diagnostic_only_no_model_change',
     'requirements':['Repeat across multiple completed seasons','Compare against the currently deployed 4.4 baseline on identical observations','Test on held-out future games before replacing production model']}
    report['version']='5.0D-validation-v1'
    return self.send_json(report)
   except ValueError as e:return self.send_json({'error':str(e)},400)
  if p=='/api/intelligence':
   q=parse_qs(urlparse(self.path).query,keep_blank_values=True)
   names=q.get('player',[]);opponents=q.get('opponent',[])
   scoring=q.get('scoring',['ppr'])[0];season=q.get('season',[''])[0]
   league=q.get('league_size',['12'])[0];before=q.get('before_week',[''])[0]
   if scoring not in ('ppr','half','standard') or not 1<=len(names)<=12 or any(not n.strip() or len(n)>100 for n in names):
    return self.send_json({'error':'Select 1-12 valid players and a scoring format'},400)
   if opponents and len(opponents)!=len(names):return self.send_json({'error':'Supply an opponent for every player or omit all opponents'},400)
   if any(x and not re.fullmatch('[A-Za-z]{2,3}',x) for x in opponents):return self.send_json({'error':'Invalid opponent'},400)
   if not league.isdigit() or not 8<=int(league)<=20:return self.send_json({'error':'League size must be 8-20'},400)
   if before and (not before.isdigit() or not 1<=int(before)<=19):return self.send_json({'error':'Invalid before_week'},400)
   if season and (not season.isdigit() or not 2000<=int(season)<=current_nfl_season()):return self.send_json({'error':'Invalid season'},400)
   try:
    with connect() as c:
     year=int(season) if season else season_latest(c)
     if year is None:return self.send_json({'error':'Import player data first'},400)
     cutoff=int(before) if before else None
     projections=[player_projection(c,name.strip(),year,scoring,opponents[i].upper() if opponents else '',before_week=cutoff) for i,name in enumerate(names)]
     # Only players with prior recorded games contribute to each position's rating reference.
     # Pool projections use no opponent adjustment, so all players are compared on equal footing.
     pools={}
     for pos in {p['position'] for p in projections}:
      if pos not in POSITIONS:continue
      pool_names=[r['player'] for r in c.execute('SELECT player FROM player_games WHERE season=? AND pos=? AND (? IS NULL OR week<?) GROUP BY player HAVING COUNT(*)>=3 ORDER BY SUM(COALESCE(targets,0)+COALESCE(rushing_yards,0)/4.0) DESC LIMIT 150',(year,pos,cutoff,cutoff)).fetchall()]
      pools[pos]=[player_projection(c,n,year,scoring,before_week=cutoff)['projected_points'] for n in pool_names]
    # Schedule data is read only from the existing local cache; never request network here.
    remaining={}
    if not cutoff and year==current_nfl_season():
     try:
      schedule=json.loads(SCHEDULE_CACHE.read_text())
      today=datetime.datetime.now(datetime.timezone.utc).date().isoformat()
      for g in schedule.get('games',[]):
       if g.get('season')==year and g.get('date','')>today:
        for t in (g.get('home'),g.get('away')):
         if t:remaining[t]=remaining.get(t,0)+1
     except (OSError,ValueError,TypeError):pass
    result=[score_player(p,pools.get(p['position'],[]),remaining.get(p['team']) if remaining else None,int(league)) for p in projections]
    return self.send_json({'model_version':MODEL,'season':year,'scoring':scoring,'league_size':int(league),
      'players':result,'start_sit':compare_weekly(result),
      'status':'research_preview_not_validated',
      'methodology':'Weekly rating is within-position percentile of existing 3.6 opportunity-adjusted projections plus a small sample-size reliability adjustment. Trade rating is provisional and withheld when the verified future schedule is unavailable. No trained new model is claimed.',
      'limitations':['Not a calibrated probability or validated trade fairness score','Position rating reference is limited to 150 high-opportunity players with 3+ recorded games per position','No injury, snaps, routes, coverage, weather or market prices connected','Trade values do not yet account for specific roster, flex slots or lineup optimization']})
   except ValueError as e:return self.send_json({'error':str(e)},400)
  if p=='/api/projection':
    q=parse_qs(urlparse(self.path).query,keep_blank_values=True)
    scoring=q.get('scoring',['ppr'])[0];season=q.get('season',[''])[0]
    names=q.get('player',[]);opponents=q.get('opponent',[])
    if scoring not in ('ppr','half','standard') or not 1<=len(names)<=2 or any(not n.strip() or len(n)>100 for n in names):
     return self.send_json({'error':'Choose one or two valid players and a scoring format'},400)
    if opponents and len(opponents)!=len(names):return self.send_json({'error':'Supply an opponent for each player, or omit opponents'},400)
    if any(x and (not re.fullmatch('[A-Za-z]{2,3}',x)) for x in opponents):return self.send_json({'error':'Invalid opponent abbreviation'},400)
    try:
     with connect() as c:
      year=int(season) if season.isdigit() else season_latest(c)
      if year is None:return self.send_json({'error':'Import player data first'},400)
      players=[player_projection(c,name.strip(),year,scoring,opponents[i].upper() if opponents else '') for i,name in enumerate(names)]
     ranked=sorted(players,key=lambda p:p['projected_points'],reverse=True)
     return self.send_json({'version':'3.6','players':players,'recommended_start':ranked[0]['name'] if len(ranked)>1 else None,
      'projection_edge':round(ranked[0]['projected_points']-ranked[1]['projected_points'],2) if len(ranked)>1 else None,
      'recommendation_basis':'Higher estimated fantasy points from the specified historical season; not a validated weekly forecast'})
    except ValueError as e:return self.send_json({'error':str(e)},400)
  if p=='/api/defense':
   q=parse_qs(urlparse(self.path).query)
   season=q.get('season',[''])[0]; scoring=q.get('scoring',['ppr'])[0]
   position=q.get('position',['WR'])[0].upper()
   if scoring not in ('ppr','half','standard') or position not in ('RB','WR','TE','QB'):
    return self.send_json({'error':'Invalid scoring or position'},400)
   with connect() as c:
    year=int(season) if season.isdigit() else season_latest(c)
    if year is None:return self.send_json({'season':None,'defenses':[]})
    rows=c.execute("SELECT * FROM player_games WHERE season=? AND pos=? AND opponent IS NOT NULL AND opponent<>'' ORDER BY week",(year,position)).fetchall()
   # Aggregate player fantasy points by defense and week, then average across observed weeks.
   # This is team-level positional fantasy points allowed, NOT per-player opponent allowance.
   weekly={}
   for r in rows:
    defense=(r['opponent'] or '').strip().upper()
    if not defense:continue
    key=(defense,int(r['week']))
    entry=weekly.setdefault(key,{'points':0.0,'players':0,'targets':0.0,'receptions':0.0,'yards':0.0,'tds':0.0})
    entry['points']+=fantasy(r,scoring);entry['players']+=1
    entry['targets']+=float(r['targets'] or 0)
    entry['receptions']+=float(r['receptions'] or 0)
    entry['yards']+=float(r['receiving_yards'] or 0)+float(r['rushing_yards'] or 0)
    entry['tds']+=float(r['receiving_tds'] or 0)+float(r['rushing_tds'] or 0)
   grouped={}
   for (team,week),entry in weekly.items():grouped.setdefault(team,[]).append((week,entry))
   defenses=[]
   for team,games in grouped.items():
    games.sort(key=lambda x:x[0]);n=len(games)
    totals={k:sum(e[k] for _,e in games) for k in ('points','targets','receptions','yards','tds')}
    last=games[-4:]
    defenses.append({'team':team,'weeks':n,'fantasy_points_allowed_per_game':round(totals['points']/n,2),
     'last_four_allowed_per_game':round(sum(e['points'] for _,e in last)/len(last),2),
     'targets_allowed_per_game':round(totals['targets']/n,1),'receptions_allowed_per_game':round(totals['receptions']/n,1),
     'yards_allowed_per_game':round(totals['yards']/n,1),'touchdowns_allowed_per_game':round(totals['tds']/n,2),
     'latest_week':games[-1][0]})
   defenses.sort(key=lambda x:x['fantasy_points_allowed_per_game'],reverse=True)
   for i,d in enumerate(defenses):d['rank_most_allowed']=i+1
   return self.send_json({'season':year,'scoring':scoring,'position':position,'defenses':defenses,
    'methodology':'Total recorded fantasy points by all players at the selected position against each opponent, divided by weeks with records. Higher means more points allowed. Includes only imported regular-season player game logs.',
    'limitations':['Historical results, not an upcoming-game projection or coverage-scheme analysis',
    'Missing/incomplete player logs can distort totals; week counts and sample sizes are displayed',
    'No opponent-adjustment, injuries, weather, defensive personnel or schedule feed']})
  if p=='/api/players':
   q=parse_qs(urlparse(self.path).query);search=q.get('q',[''])[0].strip()[:80];season=q.get('season',[''])[0];scoring=q.get('scoring',['ppr'])[0]
   if scoring not in ('ppr','half','standard'):scoring='ppr'
   with connect() as c:
    year=int(season) if season.isdigit() else season_latest(c)
    if year is None:return self.send_json({'players':[],'scoring':scoring,'demo':True,'season':None})
    sql='SELECT * FROM player_games WHERE season=?';args=[year]
    if search:sql+=' AND player LIKE ?';args.append('%'+search+'%')
    rows=c.execute(sql+' ORDER BY week DESC LIMIT 20000',args).fetchall()
   groups={}
   for r in rows:
    key=(r['player'],r['team'],r['pos']);g=groups.setdefault(key,{'name':r['player'],'team':r['team'],'pos':r['pos'],'games':0,'total':0,'recent':[]})
    g['games']+=1;g['total']+=fantasy(r,scoring)
    if len(g['recent'])<5:g['recent'].append(fantasy(r,scoring))
   players=[]
   for g in groups.values():
    g['ppg']=round(g.pop('total')/g['games'],1);g['trend']=round(sum(g['recent'])/len(g['recent']),1);players.append(g)
   players.sort(key=lambda x:x['ppg'],reverse=True)
   return self.send_json({'players':players[:100],'scoring':scoring,'demo':not bool(rows),'season':year})
  if p=='/api/leagues':
   u=self.user()
   if not u:return self.send_json({'error':'Sign in to view leagues'},401)
   with connect() as c:rows=c.execute('SELECT id,name,scoring,roster FROM leagues WHERE user_id=? ORDER BY id DESC',(u['id'],)).fetchall()
   return self.send_json({'leagues':[{'id':r['id'],'name':r['name'],'scoring':r['scoring'],'roster':json.loads(r['roster'])} for r in rows]})
  if p.startswith('/api/'):return self.send_json({'error':'Not found'},404)
  if p=='/':self.path='/index.html'
  if p.endswith('.html') or p=='/index.html':
   self.send_response(200) if False else None
  return super().do_GET()
 def do_POST(self):
  p=urlparse(self.path).path
  if p=='/api/automation/import':
   # Machine-to-machine endpoint; do not require browser Origin, but require a strong shared secret.
   expected=os.environ.get('ROSTERHELIX_CRON_TOKEN','')
   provided=self.headers.get('X-RosterHelix-Cron-Token','')
   if len(expected)<32 or not provided or not hmac.compare_digest(expected,provided):
    return self.send_json({'error':'Unauthorized'},401)
   if not IMPORT_LOCK.acquire(blocking=False):
    return self.send_json({'error':'Import already running'},409)
   season=current_nfl_season()
   try:
    count=import_nflverse_season(season)
    write_import_status('success',season,count=count)
    return self.send_json({'ok':True,'season':season,'rows_processed':count})
   except Exception as e:
    write_import_status('failed',season,error=type(e).__name__)
    print('Scheduled NFLverse import failed:',repr(e),flush=True)
    return self.send_json({'error':'Scheduled import failed; check Render logs'},502)
   finally:IMPORT_LOCK.release()
  if not self.origin_ok():return self.send_json({'error':'Same-origin request required'},403)
  p=urlparse(self.path).path
  try:raw=self.read_body()
  except ValueError as e:return self.send_json({'error':str(e)},413)
  if p=='/api/admin/nflverse/import':
   u=self.user()
   if not self.admin(u) or not self.csrf(u):return self.send_json({'error':'Administrator authorization required'},403)
   try:
    body=json.loads(raw or b'{}')
    season=body.get('season')
    if type(season) is not int or not 1999<=season<=current_nfl_season():
     return self.send_json({'error':f'Choose one season from 1999 through {current_nfl_season()}'},400)
    if not IMPORT_LOCK.acquire(blocking=False):
     return self.send_json({'error':'Another import is running; retry shortly'},409)
    try:count=import_nflverse_season(season)
    finally:IMPORT_LOCK.release()
    return self.send_json({'ok':True,'season':season,'rows_processed':count,'source':'nflverse'})
   except (ValueError,UnicodeDecodeError,KeyError,TypeError) as e:return self.send_json({'error':str(e)},400)
   except (HTTPError,URLError,TimeoutError,OSError) as e:return self.send_json({'error':'Unable to download nflverse data for this season','detail':str(e)[:160]},502)
   except sqlite3.Error:return self.send_json({'error':'Database import failed'},500)
  if p=='/api/admin/import':
   u=self.user()
   if not self.admin(u) or not self.csrf(u):return self.send_json({'error':'Administrator authorization required'},403)
   try:
    data=raw.decode('utf-8-sig');reader=csv.DictReader(io.StringIO(data));required={'season','week','player'}
    if not required.issubset(set(reader.fieldnames or [])):return self.send_json({'error':'CSV requires season, week, player columns'},400)
    cols=['season','week','player','team','pos','opponent','passing_yards','passing_tds','interceptions','rushing_yards','rushing_tds','receptions','receiving_yards','receiving_tds','targets','fumbles_lost'];batch=[]
    for row in reader:
     if len(batch)>=50000:return self.send_json({'error':'Import limit 50,000 rows per upload'},400)
     values=[int(row[k]) if k in ('season','week') else str(row.get(k,'')).strip()[:100] if k in ('player','team','pos','opponent') else float(row.get(k) or 0) for k in cols]
     if not values[2] or not (1990<=values[0]<=2100 and 1<=values[1]<=25):raise ValueError('Invalid season, week, or player')
     batch.append(values)
    with connect() as c:c.executemany('INSERT INTO player_games('+','.join(cols)+') VALUES('+','.join(['?']*len(cols))+') ON CONFLICT(season,week,player,team) DO UPDATE SET '+','.join(f'{x}=excluded.{x}' for x in cols[4:]),batch)
    return self.send_json({'ok':True,'rows_processed':len(batch)})
   except (ValueError,UnicodeDecodeError,sqlite3.Error) as e:return self.send_json({'error':str(e)},400)
  try:body=json.loads(raw or b'{}')
  except Exception:return self.send_json({'error':'Invalid JSON'},400)
  if p in ('/api/auth/register','/api/auth/login'):
   email=str(body.get('email','')).strip().lower();password=str(body.get('password',''))
   if not re.fullmatch(r'[^\s@]+@[^\s@]+\.[^\s@]+',email) or not 10<=len(password)<=128:return self.send_json({'error':'Valid email and password of at least 10 characters required'},400)
   with connect() as c:
    if p.endswith('register'):
     try:c.execute('INSERT INTO users(email,password,created) VALUES(?,?,?)',(email,hash_password(password),int(time.time())))
     except sqlite3.IntegrityError:return self.send_json({'error':'Account already exists'},409)
    u=c.execute('SELECT * FROM users WHERE email=?',(email,)).fetchone()
    if not u or not verify_password(password,u['password']):return self.send_json({'error':'Invalid credentials'},401)
    token=secrets.token_urlsafe(40);csrf=secrets.token_urlsafe(32)
    c.execute('INSERT INTO sessions VALUES(?,?,?,?)',(hashlib.sha256(token.encode()).hexdigest(),u['id'],csrf,int(time.time())+604800))
   secure='; Secure' if os.getenv('RENDER') or self.headers.get('X-Forwarded-Proto')=='https' else ''
   return self.send_json({'ok':True,'email':email,'csrf':csrf,'admin':self.admin(u) if 'csrf' in u.keys() else email==os.getenv('ADMIN_EMAIL','').strip().lower()},headers={'Set-Cookie':f'rh2_session={token}; HttpOnly; SameSite=Lax; Path=/; Max-Age=604800{secure}'})
  u=self.user()
  if not self.csrf(u):return self.send_json({'error':'Sign in and provide CSRF token'},403)
  if p=='/api/auth/logout':
   with connect() as c:c.execute('DELETE FROM sessions WHERE token_hash=?',(hashlib.sha256(self.cookie().encode()).hexdigest(),))
   return self.send_json({'ok':True},headers={'Set-Cookie':'rh2_session=; HttpOnly; SameSite=Lax; Path=/; Max-Age=0'})
  if p=='/api/leagues':
   name=str(body.get('name','')).strip()[:80];scoring=body.get('scoring','ppr');roster=body.get('roster',[])
   if not name or scoring not in ('ppr','half','standard') or not isinstance(roster,list) or len(roster)>40:return self.send_json({'error':'Invalid league'},400)
   roster=[str(x)[:100] for x in roster]
   with connect() as c:
    c.execute('INSERT INTO leagues(user_id,name,scoring,roster) VALUES(?,?,?,?)',(u['id'],name,scoring,json.dumps(roster)));id=c.execute('SELECT last_insert_rowid()').fetchone()[0]
   return self.send_json({'ok':True,'id':id})
  return self.send_json({'error':'Not found'},404)

if __name__=='__main__':
 setup();port=int(os.environ.get('PORT','8000'));print(f'RosterHelix 3.6 listening on {port}',flush=True);ThreadingHTTPServer(('0.0.0.0',port),Handler).serve_forever()
