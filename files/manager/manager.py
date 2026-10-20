#!/usr/bin/env python3
# 나만의리니지 웹 매니저 (표준 라이브러리만 사용)
import hashlib, html, http.cookies, json, os, re, secrets, shutil, socket, subprocess, sys, threading, time
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from urllib.parse import urlparse, parse_qs

APP = os.environ.get('LINEAGE_APP', '/opt/lineage')
DB = 'l1jdb_kr'
PORT = int(os.environ.get('MANAGER_PORT', '8080'))
TELNET = ('127.0.0.1', 2323)
HERE = os.path.dirname(os.path.abspath(__file__))
PWFILE = os.path.join(HERE, 'password.txt')
BACKUP_DIR = os.path.join(APP, 'backups')
SESSIONS = {}
LOCK = threading.Lock()

CLASS_NAMES = {0: '군주', 1: '기사', 2: '요정', 3: '마법사', 4: '다크엘프', 5: '용기사', 6: '환술사'}
GMCODE = 5842
BAD_BUFFS = '999,1000,1001,20081'

# ---------------------------------------------------------------- helpers
def has_systemd():
    return shutil.which('systemctl') is not None and os.path.isdir('/run/systemd/system')

def q(s):
    """SQL 문자열 이스케이프"""
    return "'" + str(s).replace('\\', '\\\\').replace("'", "''") + "'"

def sql(query, rows=True):
    p = subprocess.run(['mysql', '-uroot', '--default-character-set=utf8mb4', '-B', '-N', '--raw', DB, '-e', query],
                       capture_output=True, text=True)
    if p.returncode != 0:
        raise RuntimeError(p.stderr.strip() or 'DB 오류')
    if not rows:
        return []
    out = []
    for line in p.stdout.splitlines():
        out.append(line.split('\t'))
    return out

def telnet(cmd, timeout=4):
    try:
        s = socket.create_connection(TELNET, timeout)
        s.sendall((cmd + '\r\n').encode('utf-8'))
        s.settimeout(timeout)
        d = b''
        while d.count(b'\r\n') < 2:
            c = s.recv(65536)
            if not c:
                break
            d += c
        # 여러 줄 결과(online) 마저 받기
        s.settimeout(0.3)
        try:
            while True:
                c = s.recv(65536)
                if not c:
                    break
                d += c
        except Exception:
            pass
        s.close()
        txt = d.decode('utf-8', 'replace')
        head, _, body = txt.partition('\r\n')
        return head.startswith('0 '), body.strip('\r\n')
    except Exception as e:
        return False, 'server-offline'

def online_players():
    ok, body = telnet('online')
    res = {}
    if ok and body:
        for line in body.split('\r\n'):
            f = line.split('\t')
            if len(f) >= 7:
                res[f[0]] = {'account': f[1], 'level': f[2], 'map': f[3], 'x': f[4], 'y': f[5], 'gm': f[6] == '1'}
    return res

def server_status():
    if has_systemd():
        st = subprocess.run(['systemctl', 'is-active', 'lineage'], capture_output=True, text=True).stdout.strip()
        return st
    return 'active' if subprocess.run(['pgrep', '-f', 'solo.Main'], capture_output=True).returncode == 0 else 'inactive'

def server_ctl(action):
    if has_systemd():
        subprocess.run(['systemctl', action, 'lineage'])
    else:
        if action in ('stop', 'restart'):
            subprocess.run(['pkill', '-f', 'solo.Main'])
            time.sleep(2)
        if action in ('start', 'restart'):
            subprocess.Popen([os.path.join(APP, 'run.sh')], stdout=open(os.path.join(APP, 'log', 'console.log'), 'ab'),
                             stderr=subprocess.STDOUT, start_new_session=True)

def char_row(name):
    r = sql('SELECT objid, account_name FROM characters WHERE char_name=%s' % q(name))
    if not r:
        raise RuntimeError('캐릭터를 찾을 수 없습니다')
    return int(r[0][0]), r[0][1]

def make_offline(name):
    """접속 중이면 저장 후 접속 종료"""
    if name in online_players():
        telnet('save ' + name)
        telnet('kick ' + name)
        for _ in range(20):
            time.sleep(0.5)
            if name not in online_players():
                break
        time.sleep(1.5)
        return True
    return False

def read_props(path):
    return open(path, 'rb').read().decode('cp949')

def write_props(path, text):
    open(path, 'wb').write(text.encode('cp949'))

RATE_KEYS = [('RateXp', '경험치 배율'), ('RateDropAdena', '아데나 배율'), ('RateDropItems', '아이템 드랍 배율'),
             ('EnchantChanceWeapon', '무기 인챈트 확률 가산(%p)'), ('EnchantChanceArmor', '방어구 인챈트 확률 가산(%p)'),
             ('EnchantChanceAccessory', '장신구 인챈트 확률 가산(%p)'), ('RateWeightLimit', '무게 한도 배율')]

SOLO_KEYS = [('NpcDamageRate', '몹에게 받는 데미지 % (100=원래, 30=30%만, 0=무적) · 즉시 적용', '30'),
             ('FullHealPotion', '토끼의 간 완전회복 (1=켜기, 0=끄기) · 즉시 적용', '1')]
ALT_KEYS = [('WarTime', '공성전 진행 시간 (예: 1h, 30m) · 재시작 후 적용')]

def get_settings():
    t = read_props(os.path.join(APP, 'config', 'rates.properties'))
    rates = []
    for k, label in RATE_KEYS:
        m = re.search(r'(?m)^%s\s*=\s*(\S+)' % k, t)
        rates.append({'key': k, 'label': label, 'value': m.group(1) if m else ''})
    ap = os.path.join(APP, 'config', 'altsettings.properties')
    at = read_props(ap) if os.path.isfile(ap) else ''
    for k, label in ALT_KEYS if at else []:
        m = re.search(r'(?m)^%s\s*=\s*(\S+)' % k, at)
        rates.append({'key': k, 'label': label, 'value': m.group(1) if m else ''})
    sp = os.path.join(APP, 'config', 'solo.properties')
    st = open(sp, encoding='utf-8').read() if os.path.isfile(sp) else ''
    for k, label, default in SOLO_KEYS:
        m = re.search(r'(?m)^%s\s*=\s*(\S+)' % k, st)
        rates.append({'key': k, 'label': label, 'value': m.group(1) if m else default})
    bc = open(os.path.join(APP, 'data', 'xml', 'Cycle', 'BossCycle.xml'), encoding='utf-8-sig').read()
    m = re.search(r'Name="SOLO20">\s*<Cycle Period="(\d+)m"', bc)
    return {'rates': rates, 'boss_minutes': int(m.group(1)) if m else 20}

def save_settings(data):
    path = os.path.join(APP, 'config', 'rates.properties')
    t = read_props(path)
    for k, _ in RATE_KEYS:
        if k in data:
            v = str(data[k]).strip()
            if not re.fullmatch(r'\d+(\.\d+)?', v):
                raise RuntimeError('%s 값이 숫자가 아닙니다' % k)
            t = re.sub(r'(?m)^%s\s*=.*$' % k, '%s = %s' % (k, v), t)
    write_props(path, t)
    ap = os.path.join(APP, 'config', 'altsettings.properties')
    at = read_props(ap) if os.path.isfile(ap) else ''
    for k, _ in ALT_KEYS if at else []:
        if k in data:
            v = str(data[k]).strip()
            if not re.fullmatch(r'\d+[dhm]', v):
                raise RuntimeError('%s 값은 숫자+단위(d/h/m) 형식이어야 합니다 (예: 1h)' % k)
            at = re.sub(r'(?m)^%s\s*=.*$' % k, '%s = %s' % (k, v), at)
    if at:
        write_props(ap, at)
    sp = os.path.join(APP, 'config', 'solo.properties')
    st = open(sp, encoding='utf-8').read() if os.path.isfile(sp) else ''
    for k, _, _ in SOLO_KEYS:
        if k in data:
            v = str(data[k]).strip()
            if not re.fullmatch(r'\d+', v):
                raise RuntimeError('%s 값이 숫자가 아닙니다' % k)
            if re.search(r'(?m)^%s\s*=' % k, st):
                st = re.sub(r'(?m)^%s\s*=.*$' % k, '%s = %s' % (k, v), st)
            else:
                st += '\n%s = %s\n' % (k, v)
    open(sp, 'w', encoding='utf-8').write(st)
    if 'boss_minutes' in data:
        n = int(data['boss_minutes'])
        if n < 1 or n > 1440:
            raise RuntimeError('보스 주기는 1~1440분')
        bp = os.path.join(APP, 'data', 'xml', 'Cycle', 'BossCycle.xml')
        bc = open(bp, encoding='utf-8-sig').read()
        bc = re.sub(r'(Name="SOLO20">\s*<Cycle Period=")\d+m(" Start="1m" End=")\d+m',
                    lambda m: '%s%dm%s%dm' % (m.group(1), n, m.group(2), max(1, min(3, n - 1))), bc)
        open(bp, 'w', encoding='utf-8-sig').write(bc)

def do_backup(tag='수동'):
    os.makedirs(BACKUP_DIR, exist_ok=True)
    telnet('save')
    name = time.strftime('%Y%m%d_%H%M%S') + '_' + tag + '.sql.gz'
    path = os.path.join(BACKUP_DIR, name)
    with open(path, 'wb') as f:
        p1 = subprocess.Popen(['mysqldump', '-uroot', '--default-character-set=utf8', '--single-transaction', DB], stdout=subprocess.PIPE)
        p2 = subprocess.Popen(['gzip', '-c'], stdin=p1.stdout, stdout=f)
        p1.stdout.close(); p2.communicate(); p1.wait()
    if p1.returncode != 0:
        os.remove(path)
        raise RuntimeError('백업 실패')
    return name

def list_backups():
    if not os.path.isdir(BACKUP_DIR):
        return []
    out = []
    for f in sorted(os.listdir(BACKUP_DIR), reverse=True):
        if f.endswith('.sql.gz'):
            out.append({'name': f, 'size': os.path.getsize(os.path.join(BACKUP_DIR, f))})
    return out

def restore_backup(name):
    if '/' in name or not name.endswith('.sql.gz'):
        raise RuntimeError('잘못된 파일')
    path = os.path.join(BACKUP_DIR, name)
    if not os.path.isfile(path):
        raise RuntimeError('백업 파일이 없습니다')
    do_backup('복원전자동')
    server_ctl('stop')
    time.sleep(3)
    p = subprocess.run('gunzip -c %s | mysql -uroot --default-character-set=utf8 %s' % (shlex_quote(path), DB), shell=True,
                       capture_output=True, text=True)
    server_ctl('start')
    if p.returncode != 0:
        raise RuntimeError('복원 실패: ' + p.stderr[-300:])

def shlex_quote(s):
    import shlex
    return shlex.quote(s)

# ---------------------------------------------------------------- API
def api(path, data):
    if path == 'status':
        on = online_players()
        acc = sql('SELECT COUNT(*) FROM accounts')[0][0]
        chars = sql('SELECT COUNT(*) FROM characters')[0][0]
        return {'server': server_status(), 'online': list(on.keys()), 'accounts': acc, 'characters': chars,
                'telnet': telnet('echo ok')[0]}

    if path == 'server':
        act = data.get('action')
        if act not in ('start', 'stop', 'restart'):
            raise RuntimeError('잘못된 동작')
        if act in ('stop', 'restart'):
            telnet('notice 서버가 곧 %s됩니다.' % ('재시작' if act == 'restart' else '종료'))
            telnet('save')
            time.sleep(1)
        server_ctl(act)
        return {'msg': {'start': '서버를 켰습니다. 30초~1분 뒤 접속하세요.', 'stop': '서버를 껐습니다.',
                        'restart': '서버를 재시작합니다. 30초~1분 뒤 접속하세요.'}[act]}

    if path == 'notice':
        ok, _ = telnet('notice ' + data.get('text', '').replace('\n', ' ')[:200])
        return {'msg': '공지를 보냈습니다.' if ok else '서버가 꺼져 있습니다.'}

    if path == 'chars':
        on = online_players()
        rows = sql('SELECT c.char_name, c.account_name, c.Type, c.level, c.AccessLevel, c.MapID, IFNULL(m.locationname,""), '
                   'c.LocX, c.LocY, IFNULL(a.access_level,0), IFNULL(a.quize,"") FROM characters c '
                   'LEFT JOIN mapids m ON m.mapid=c.MapID LEFT JOIN accounts a ON a.login=c.account_name ORDER BY c.level DESC')
        out = []
        for r in rows:
            name = r[0]
            o = on.get(name)
            out.append({'name': name, 'account': r[1], 'cls': CLASS_NAMES.get(int(r[2] or 0), r[2]),
                        'level': o['level'] if o else r[3], 'gm': int(r[4] or 0) == GMCODE, 'map': r[6] or r[5],
                        'online': bool(o), 'quiz': bool(r[10])})
        return {'chars': out}

    if path == 'char_action':
        name = data['name']
        act = data['action']
        objid, account = char_row(name)
        on = name in online_players()

        if act == 'gm_on' or act == 'gm_off':
            lvl = GMCODE if act == 'gm_on' else 0
            was = make_offline(name)
            sql('UPDATE characters SET AccessLevel=%d WHERE objid=%d' % (lvl, objid), rows=False)
            sql('UPDATE accounts SET access_level=%d WHERE login=%s' % (lvl, q(account)), rows=False)
            return {'msg': ('GM으로 지정했습니다.' if lvl else 'GM을 해제했습니다.') + (' 접속을 끊었으니 다시 접속하세요.' if was else '')}
        if act == 'clear_buff':
            was = make_offline(name)
            sql('DELETE FROM character_buff WHERE char_obj_id=%d' % objid, rows=False)
            return {'msg': '버프를 초기화했습니다.' + (' 다시 접속하세요.' if was else '')}
        if act == 'reset_ui':
            was = make_offline(name)
            sql('DELETE FROM character_config WHERE object_id=%d' % objid, rows=False)
            return {'msg': '창 배치·단축키 설정을 초기화했습니다.' + (' 다시 접속하세요.' if was else '')}
        if act == 'quiz_off':
            sql('UPDATE accounts SET quize=%s WHERE login=%s' % (q('1234'), q(account)), rows=False)
            return {'msg': '퀴즈 경고를 껐습니다. (다음 접속부터)'}
        if act == 'unstuck':
            if on:
                before = online_players().get(name, {}).get('map')
                telnet('gm %s 귀환 5' % name)
                time.sleep(1.5)
                after = online_players().get(name, {}).get('map')
                if after == '4' or (after and after != before):
                    return {'msg': '기란 마을로 이동시켰습니다.'}
                # 이동이 안 먹으면(캐릭터 잠김) 저장 후 접속을 끊고 위치를 바꿈
                make_offline(name)
            sql('UPDATE characters SET LocX=33442, LocY=32797, MapID=4 WHERE objid=%d' % objid, rows=False)
            return {'msg': '접속을 끊었습니다. 다시 접속하면 기란 마을에서 시작합니다.' if on else '다음 접속 때 기란 마을에서 시작합니다.'}
        if act == 'unequip_high':
            was = make_offline(name)
            sql('UPDATE character_items SET is_equipped=0 WHERE char_id=%d AND enchantlvl>127' % objid, rows=False)
            return {'msg': '+127 초과 장비의 착용을 풀었습니다.' + (' 다시 접속하세요.' if was else '')}
        if act == 'kick':
            if not on:
                return {'msg': '접속 중이 아닙니다.'}
            make_offline(name)
            return {'msg': '저장 후 접속을 끊었습니다.'}

        # 아래는 접속 중일 때만 (게임 안 GM 명령으로 실행)
        if not on:
            raise RuntimeError('게임에 접속 중일 때만 사용할 수 있습니다.')
        def num(k, lo, hi):
            v = int(data.get(k, 0))
            if v < lo or v > hi:
                raise RuntimeError('%s 값은 %d~%d' % (k, lo, hi))
            return v
        if act == 'level':
            cmd = '레벨 %d' % num('value', 1, 99)
        elif act == 'adena':
            cmd = '아데나 %d' % num('value', 1, 2000000000)
        elif act == 'item':
            cmd = '아이템 %d %d %d' % (num('item_id', 1, 99999999), num('count', 1, 100000), num('enchant', -10, 100000))
        elif act == 'poly':
            cmd = '변신 %s %d' % (name, num('value', 0, 99999))
        elif act == 'teleport':
            cmd = '귀환 %d' % num('value', 1, 33)
        elif act == 'hunt':
            cmd = '사냥터 %d' % num('value', 1, 18)
        elif act == 'spawn':
            cmd = '몬스터 %d %d' % (num('npc_id', 1, 99999999), num('count', 1, 50))
        elif act == 'skills':
            cmd = '스킬마스터'
        elif act == 'allbuff':
            cmd = '올버프 %s' % name
        elif act == 'speed':
            cmd = '속도'
        else:
            raise RuntimeError('알 수 없는 동작')
        ok, body = telnet('gm %s %s' % (name, cmd))
        if not ok:
            raise RuntimeError('실행 실패: ' + body)
        return {'msg': '실행했습니다. 게임 화면을 확인하세요.'}

    if path == 'items':
        kw = data.get('q', '').strip()
        if not kw:
            return {'items': []}
        like = q('%' + kw + '%')
        rows = sql('(SELECT item_id, name, "무기" FROM weapon WHERE name LIKE %s) UNION ALL '
                   '(SELECT item_id, name, "방어구" FROM armor WHERE name LIKE %s) UNION ALL '
                   '(SELECT item_id, name, "기타" FROM etcitem WHERE name LIKE %s) ORDER BY 1 LIMIT 200' % (like, like, like))
        return {'items': [{'id': r[0], 'name': r[1], 'type': r[2]} for r in rows]}

    if path == 'npcs':
        kw = data.get('q', '').strip()
        boss = data.get('boss')
        if boss:
            rows = sql('SELECT DISTINCT n.npcid, n.name, n.lvl, n.hp FROM spawnlist_boss b JOIN npc n ON n.npcid=b.npc_id ORDER BY n.lvl DESC')
        elif kw:
            rows = sql('SELECT npcid, name, lvl, hp FROM npc WHERE name LIKE %s AND impl LIKE "%%Monster%%" ORDER BY lvl DESC LIMIT 200' % q('%' + kw + '%'))
        else:
            rows = []
        return {'npcs': [{'id': r[0], 'name': r[1], 'lvl': r[2], 'hp': r[3]} for r in rows]}

    if path == 'polys':
        rows = sql('SELECT polyid, name, minlevel FROM polymorphs ORDER BY minlevel, name')
        return {'polys': [{'id': r[0], 'name': r[1], 'lvl': r[2]} for r in rows]}

    if path == 'settings':
        return get_settings()
    if path == 'settings_save':
        save_settings(data)
        return {'msg': '저장했습니다. [서버 재시작]을 눌러야 적용됩니다.'}

    if path == 'siege':
        ok, body = telnet('castles')
        if not ok:
            raise RuntimeError('서버가 꺼져 있거나 응답이 없습니다')
        castles = []
        for line in body.split('\r\n'):
            f = line.split('\t')
            if len(f) >= 6:
                castles.append({'id': int(f[0]), 'name': f[1], 'clan': f[2], 'leader': f[3], 'war_time': f[4], 'war': f[5] == '1'})
        ok, body = telnet('clans')
        clans = []
        for line in (body.split('\r\n') if ok else []):
            f = line.split('\t')
            if len(f) >= 3 and f[0]:
                clans.append({'name': f[0], 'leader': f[1], 'castle': int(f[2] or 0)})
        return {'castles': castles, 'clans': clans}
    if path == 'siege_start':
        cid = int(data['castle']); mins = int(data.get('minutes', 1))
        if mins < 0 or mins > 10080:
            raise RuntimeError('시작 시간은 0~10080분')
        ok, body = telnet('warstart %d %d' % (cid, mins))
        if not ok:
            raise RuntimeError({'already at war': '이미 공성전 중입니다'}.get(body, '시작 실패: ' + body))
        return {'msg': ('공성전이 시작됩니다' if mins == 0 else '%d분 후 공성전이 시작됩니다' % mins) + ' (진행 시간은 [설정]의 공성전 진행 시간)'}
    if path == 'siege_stop':
        ok, body = telnet('warstop %d' % int(data['castle']))
        if not ok:
            raise RuntimeError({'not at war': '공성전 중이 아닙니다'}.get(body, '종료 실패: ' + body))
        return {'msg': '공성전을 끝냈습니다.'}
    if path == 'castle_owner':
        clan = (data.get('clan') or '').strip() or '-'
        if '\r' in clan or '\n' in clan:
            raise RuntimeError('잘못된 혈맹 이름')
        ok, body = telnet('castleowner %d %s' % (int(data['castle']), clan))
        if not ok:
            raise RuntimeError({'no clan': '그 혈맹이 없습니다', 'clan already owns another castle': '그 혈맹은 이미 다른 성을 가지고 있습니다'}.get(body, '변경 실패: ' + body))
        return {'msg': '성 주인을 바꿨습니다.' if clan != '-' else 'NPC 소유로 되돌렸습니다.'}

    if path == 'backups':
        return {'backups': list_backups()}
    if path == 'backup_now':
        return {'msg': '백업했습니다: ' + do_backup()}
    if path == 'backup_restore':
        restore_backup(data['name'])
        return {'msg': '복원했습니다. 서버를 다시 켰으니 30초~1분 뒤 접속하세요.'}
    if path == 'backup_delete':
        n = data['name']
        if '/' in n or not n.endswith('.sql.gz'):
            raise RuntimeError('잘못된 파일')
        os.remove(os.path.join(BACKUP_DIR, n))
        return {'msg': '삭제했습니다.'}

    if path == 'password':
        new = data.get('new', '')
        if len(new) < 4:
            raise RuntimeError('비밀번호는 4자 이상')
        open(PWFILE, 'w').write(new)
        return {'msg': '비밀번호를 바꿨습니다.'}

    raise RuntimeError('알 수 없는 요청')

# ---------------------------------------------------------------- HTTP
def password():
    try:
        return open(PWFILE).read().strip()
    except Exception:
        return 'lineage'

class H(BaseHTTPRequestHandler):
    def log_message(self, *a):
        pass

    def authed(self):
        c = http.cookies.SimpleCookie(self.headers.get('Cookie', ''))
        t = c.get('sid')
        return t is not None and t.value in SESSIONS

    def send(self, code, body, ctype='application/json; charset=utf-8', extra=None):
        b = body if isinstance(body, bytes) else body.encode('utf-8')
        self.send_response(code)
        self.send_header('Content-Type', ctype)
        self.send_header('Content-Length', str(len(b)))
        self.send_header('Cache-Control', 'no-store')
        for k, v in (extra or {}).items():
            self.send_header(k, v)
        self.end_headers()
        self.wfile.write(b)

    def do_GET(self):
        u = urlparse(self.path)
        if u.path == '/':
            page = open(os.path.join(HERE, 'index.html'), encoding='utf-8').read()
            return self.send(200, page, 'text/html; charset=utf-8')
        if u.path.startswith('/download/') and self.authed():
            n = u.path[len('/download/'):]
            p = os.path.join(BACKUP_DIR, os.path.basename(n))
            if os.path.isfile(p):
                return self.send(200, open(p, 'rb').read(), 'application/gzip',
                                 {'Content-Disposition': 'attachment; filename="%s"' % os.path.basename(p).encode('ascii', 'ignore').decode()})
        self.send(404, '{}')

    def do_POST(self):
        u = urlparse(self.path)
        n = int(self.headers.get('Content-Length', 0) or 0)
        try:
            data = json.loads(self.rfile.read(n) or b'{}')
        except Exception:
            data = {}
        if u.path == '/api/login':
            if secrets.compare_digest(str(data.get('password', '')), password()):
                t = secrets.token_hex(16)
                SESSIONS[t] = time.time()
                return self.send(200, json.dumps({'ok': True}),
                                 extra={'Set-Cookie': 'sid=%s; Path=/; HttpOnly; SameSite=Strict; Max-Age=2592000' % t})
            time.sleep(1)
            return self.send(401, json.dumps({'error': '비밀번호가 틀렸습니다'}, ensure_ascii=False))
        if not self.authed():
            return self.send(401, json.dumps({'error': 'login'}))
        if not u.path.startswith('/api/'):
            return self.send(404, '{}')
        try:
            with LOCK if u.path[5:] in ('server', 'backup_restore') else _nolock():
                res = api(u.path[5:], data)
            self.send(200, json.dumps(res, ensure_ascii=False))
        except Exception as e:
            self.send(400, json.dumps({'error': str(e)}, ensure_ascii=False))

class _nolock:
    def __enter__(self): return self
    def __exit__(self, *a): return False

if __name__ == '__main__':
    if not os.path.exists(PWFILE):
        open(PWFILE, 'w').write(str(secrets.randbelow(900000) + 100000))
        os.chmod(PWFILE, 0o600)
    srv = ThreadingHTTPServer(('0.0.0.0', PORT), H)
    print('manager on :%d' % PORT, flush=True)
    srv.serve_forever()
