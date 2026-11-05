"""Safe name lookup across imported NFL game logs.

Supports first/last/full name when full names exist, and aliases for abbreviated
records when a corresponding full name is present in another imported season.
Never invents a full name from an initial.
"""
import re
import unicodedata

def normalize(value):
    text=unicodedata.normalize('NFKD',str(value or ''))
    text=''.join(ch for ch in text if not unicodedata.combining(ch)).lower()
    return re.sub(r'[^a-z0-9]+',' ',text).strip()

def _matches(term, name):
    q=normalize(term);n=normalize(name)
    if not q:return True
    if q in n:return True
    parts=q.split();tokens=n.split()
    return all(any(t.startswith(p) for t in tokens) for p in parts)

def _names(conn,season):
    rows=conn.execute('SELECT player,MAX(pos) pos,MAX(team) team,COUNT(*) games FROM player_games WHERE season=? GROUP BY player',(season,)).fetchall()
    return [dict(r) for r in rows]

def _aliases(conn):
    # A full first name from an imported season can disambiguate initials in
    # another season. Do not map initials when multiple full names conflict.
    names=[r[0] for r in conn.execute('SELECT DISTINCT player FROM player_games').fetchall()]
    by_key={}
    for name in names:
        tokens=normalize(name).split()
        if len(tokens)<2 or len(tokens[0])<2:continue
        key=(tokens[0][0],tokens[-1])
        by_key.setdefault(key,set()).add(name)
    result={}
    for name in names:
        tokens=normalize(name).split()
        if len(tokens)<2 or len(tokens[0])!=1:continue
        possibilities=by_key.get((tokens[0],tokens[-1]),set())
        if len(possibilities)==1:result[name]=next(iter(possibilities))
    return result

def search_players(conn,season,term,limit=75):
    entries=_names(conn,season)
    if not term:
        entries.sort(key=lambda r:(-r['games'],r['player']))
        return entries[:limit]
    aliases=_aliases(conn)
    hits=[]
    for row in entries:
        name=row['player'];alias=aliases.get(name,'')
        if _matches(term,name) or (alias and _matches(term,alias)):
            row['display_name']=alias or name
            rank=0 if normalize(name).startswith(normalize(term)) or normalize(alias).startswith(normalize(term)) else 1
            hits.append((rank,-row['games'],name,row))
    hits.sort(key=lambda x:x[:3])
    return [r for *_,r in hits[:limit]]

def matching_player_names(conn,season,term,limit=120):
    return [r['player'] for r in search_players(conn,season,term,limit)]
