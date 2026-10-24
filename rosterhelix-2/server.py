import csv, io, json, os, re, secrets, sqlite3, hashlib, hmac, base64, time
from http.server import ThreadingHTTPServer, SimpleHTTPRequestHandler
from pathlib import Path
from urllib.parse import urlparse, parse_qs
from http.cookies import SimpleCookie

ROOT=Path(__file__).resolve().parent
DATA=Path(os.environ.get('ROSTERHELIX_DATA_DIR',str(ROOT/'data')))
DB=DATA/'rosterhelix.sqlite3'
DATA.mkdir(parents=True,exist_ok=True)
MAX_BODY=8*1024*1024

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
CREATE INDEX IF NOT EXISTS idx_pg_player ON player_games(player,season,week);''')

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
  if p=='/api/health':return self.send_json({'ok':True,'version':'2.0'})
  if p=='/api/auth/me':
   u=self.user();return self.send_json({'authenticated':bool(u),'email':u['email'] if u else None,'csrf':u['csrf'] if u else None,'admin':self.admin(u)})
  if p=='/api/stats':
   with connect() as c:
    count=c.execute('SELECT count(*) n,count(DISTINCT player) players,min(season) first,max(season) last FROM player_games').fetchone()
   return self.send_json({'games':count['n'],'players':count['players'],'first_season':count['first'],'last_season':count['last'],'demo':count['n']==0})
  if p=='/api/players':
   q=parse_qs(urlparse(self.path).query);search=q.get('q',[''])[0].strip()[:80];season=q.get('season',[''])[0];scoring=q.get('scoring',['ppr'])[0]
   if scoring not in ('ppr','half','standard'):scoring='ppr'
   with connect() as c:
    sql='SELECT * FROM player_games WHERE player LIKE ?';args=['%'+search+'%']
    if season.isdigit():sql+=' AND season=?';args.append(int(season))
    rows=c.execute(sql+' ORDER BY season DESC,week DESC LIMIT 20000',args).fetchall()
   groups={}
   for r in rows:
    key=(r['player'],r['team'],r['pos']);g=groups.setdefault(key,{'name':r['player'],'team':r['team'],'pos':r['pos'],'games':0,'total':0,'recent':[]})
    g['games']+=1;g['total']+=fantasy(r,scoring)
    if len(g['recent'])<5:g['recent'].append(fantasy(r,scoring))
   players=[]
   for g in groups.values():
    g['ppg']=round(g.pop('total')/g['games'],1);g['trend']=round(sum(g['recent'])/len(g['recent']),1);players.append(g)
   players.sort(key=lambda x:x['ppg'],reverse=True)
   return self.send_json({'players':players[:100],'scoring':scoring,'demo':not bool(rows)})
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
  if not self.origin_ok():return self.send_json({'error':'Same-origin request required'},403)
  p=urlparse(self.path).path
  try:raw=self.read_body()
  except ValueError as e:return self.send_json({'error':str(e)},413)
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
 setup();port=int(os.environ.get('PORT','8000'));print(f'RosterHelix 2.0 listening on {port}',flush=True);ThreadingHTTPServer(('0.0.0.0',port),Handler).serve_forever()
