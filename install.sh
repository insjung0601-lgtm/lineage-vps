#!/usr/bin/env bash
# 나만의리니지 VPS 설치 스크립트 (Ubuntu 24.04)
# 사용: curl -fsSL https://raw.githubusercontent.com/insjung0601-lgtm/lineage-vps/main/install.sh | bash
set -euo pipefail

REPO_RAW="${REPO_RAW:-https://raw.githubusercontent.com/insjung0601-lgtm/lineage-vps/main}"
SRC_ZIP="${SRC_ZIP:-https://github.com/hillpath/L1J-KR_3.80/archive/refs/heads/master.zip}"
APP=/opt/lineage
DB=l1jdb_kr
DBUSER=l1j
DBPASS=l1jpass
SKIP_SYSTEM="${SKIP_SYSTEM:-0}"   # 1 이면 tailscale/방화벽/systemd 생략 (테스트용)

say(){ echo; echo "==== $* ===="; }

[ "$(id -u)" = "0" ] || { echo "root 로 실행하세요"; exit 1; }

say "1/7 패키지 설치 (Java 8, MariaDB)"
export DEBIAN_FRONTEND=noninteractive
export NEEDRESTART_MODE=l
if [ "$SKIP_SYSTEM" != "1" ]; then
  # 새 VPS 첫 부팅 때 자동 업데이트가 돌면서 DB를 재시작하는 것을 막음
  systemctl stop unattended-upgrades apt-daily.timer apt-daily-upgrade.timer 2>/dev/null || true
  for i in $(seq 1 60); do
    pgrep -f "unattended-upgr|apt-get|dpkg" >/dev/null || break
    [ "$i" = "1" ] && echo "자동 업데이트가 끝나기를 기다리는 중..."
    sleep 5
  done
fi
apt-get update -q
apt-get install -y -q openjdk-8-jre-headless mariadb-server unzip curl ca-certificates
JAVA8=/usr/lib/jvm/java-8-openjdk-amd64/bin/java
[ -x "$JAVA8" ] || { echo "Java 8 설치 실패"; exit 1; }
mkdir -p /etc/mysql/mariadb.conf.d
cat > /etc/mysql/mariadb.conf.d/99-lineage.cnf <<'EOF2'
[mysqld]
max_allowed_packet = 256M
innodb_buffer_pool_size = 512M
bind-address = 127.0.0.1
EOF2
if [ "$SKIP_SYSTEM" != "1" ]; then systemctl enable mariadb; systemctl restart mariadb; fi

say "2/7 서버 소스 내려받기"
if [ ! -f "$APP/linfree.jar.orig" ]; then
  tmp=$(mktemp -d)
  curl -fsSL -o "$tmp/src.zip" "$SRC_ZIP"
  unzip -q "$tmp/src.zip" -d "$tmp"
  rm -rf "$APP"
  mv "$tmp/L1J-KR_3.80-master" "$APP"
  rm -rf "$tmp"
  cp "$APP/linfree.jar" "$APP/linfree.jar.orig"
  mkdir -p "$APP/backup_original/config" "$APP/backup_original/data/xml/Cycle"
  cp "$APP/config/server.properties" "$APP/config/rates.properties" "$APP/backup_original/config/"
  cp "$APP/data/xml/Cycle/BossCycle.xml" "$APP/backup_original/data/xml/Cycle/"
else
  echo "이미 설치됨 - 소스 다운로드 생략"
fi

say "3/7 1인용 설정·패치 적용"
for f in linfree.jar config/server.properties config/rates.properties data/xml/Cycle/BossCycle.xml; do
  curl -fsSL -o "$APP/$f" "$REPO_RAW/files/$f"
done
mkdir -p "$APP/sql"
for f in 02_solo_tuning.sql 03_poly_korean.sql; do
  curl -fsSL -o "$APP/sql/$f" "$REPO_RAW/files/sql/$f"
done
mkdir -p "$APP/log" "$APP/emblem" "$APP/backups"

say "4/7 데이터베이스"
mysql -uroot -e "CREATE DATABASE IF NOT EXISTS $DB DEFAULT CHARACTER SET euckr;
CREATE USER IF NOT EXISTS '$DBUSER'@'localhost' IDENTIFIED BY '$DBPASS';
CREATE USER IF NOT EXISTS '$DBUSER'@'127.0.0.1' IDENTIFIED BY '$DBPASS';
GRANT ALL ON $DB.* TO '$DBUSER'@'localhost'; GRANT ALL ON $DB.* TO '$DBUSER'@'127.0.0.1'; FLUSH PRIVILEGES;"
OK=$(mysql -uroot -N -e "SELECT COUNT(*) FROM information_schema.tables WHERE table_schema='$DB' AND table_name='solo_install_ok'")
if [ "$OK" = "0" ]; then
  done_import=0
  for try in 1 2 3; do
    echo "게임 데이터 가져오는 중 (1~2분) - 시도 $try"
    if [ "$SKIP_SYSTEM" != "1" ]; then systemctl start mariadb; fi
    for i in $(seq 1 30); do mysqladmin -uroot ping >/dev/null 2>&1 && break; sleep 2; done
    mysql -uroot -e "DROP DATABASE IF EXISTS $DB; CREATE DATABASE $DB DEFAULT CHARACTER SET euckr;
      GRANT ALL ON $DB.* TO '$DBUSER'@'localhost'; GRANT ALL ON $DB.* TO '$DBUSER'@'127.0.0.1'; FLUSH PRIVILEGES;"
    if mysql -uroot --default-character-set=utf8 --max-allowed-packet=256M "$DB" < "$APP/db/anfro.sql"; then
      done_import=1; break
    fi
    echo "가져오기 실패 - 10초 후 다시 시도"
    if [ "$SKIP_SYSTEM" != "1" ]; then journalctl -u mariadb -n 15 --no-pager || true; fi
    sleep 10
  done
  [ "$done_import" = "1" ] || { echo "DB 가져오기 3회 실패. 이 화면을 캡처해서 보내주세요."; exit 1; }
  # 원본 DB에 딸려온 남의 캐릭터/계정 정리
  mysql -uroot "$DB" -e "DELETE FROM character_items; DELETE FROM characters; DELETE FROM accounts;
    CREATE TABLE solo_install_ok (done_at DATETIME); INSERT INTO solo_install_ok VALUES (NOW());"
else
  echo "기존 DB 유지 (캐릭터 보존)"
fi
mysql -uroot "$DB" < "$APP/sql/02_solo_tuning.sql"
mysql -uroot --default-character-set=utf8 "$DB" < "$APP/sql/03_poly_korean.sql"

say "5/7 서버 서비스 등록"
cat > "$APP/run.sh" <<EOF
#!/bin/sh
cd $APP
exec $JAVA8 -Djava.awt.headless=true -Djavax.accessibility.assistive_technologies=" " -Xms512m -Xmx2048m \\
 -cp "linfree.jar:lib/c3p0-0.9.1.2.jar:lib/mysql-connector-java-5.1.15-bin.jar:lib/javolution-5.5.1.jar:lib/JTattoo.jar:lib/Authentication.jar:lib/mina-core-2.0.7.jar:lib/log4j.jar:lib/jdom.jar" server.Start
EOF
chmod +x "$APP/run.sh"
if [ "$SKIP_SYSTEM" != "1" ]; then
  cat > /etc/systemd/system/lineage.service <<EOF
[Unit]
Description=Lineage L1J-KR 3.80 server
After=network-online.target mariadb.service
Requires=mariadb.service

[Service]
WorkingDirectory=$APP
ExecStart=$APP/run.sh
Restart=on-failure
RestartSec=10
StandardOutput=append:$APP/log/console.log
StandardError=append:$APP/log/console.log

[Install]
WantedBy=multi-user.target
EOF
  systemctl daemon-reload
  systemctl enable lineage
  systemctl restart lineage
fi

if [ "$SKIP_SYSTEM" != "1" ]; then
  say "6/7 Tailscale (사설 네트워크)"
  if ! command -v tailscale >/dev/null; then curl -fsSL https://tailscale.com/install.sh | sh; fi
  systemctl enable --now tailscaled
  if ! tailscale status >/dev/null 2>&1; then
    echo
    echo ">>> 아래에 나오는 https://login.tailscale.com/... 주소를 브라우저에서 열어 로그인하세요."
    echo ">>> (주인님 PC에서 Tailscale 깔 때 쓴 것과 같은 계정)"
    tailscale up --hostname=lineage-vps
  fi

  say "7/7 방화벽 (게임 포트는 Tailscale 안에서만)"
  apt-get install -y -q ufw
  ufw --force reset >/dev/null
  ufw default deny incoming
  ufw default allow outgoing
  ufw allow 22/tcp
  ufw allow in on tailscale0
  ufw --force enable
fi

say "완료"
if [ "$SKIP_SYSTEM" != "1" ]; then
  sleep 15
  systemctl is-active lineage && echo "게임 서버: 실행 중"
  TSIP=$(tailscale ip -4 2>/dev/null | head -1 || true)
  echo
  echo "=========================================="
  echo " 접속기 서버 주소(IP): ${TSIP:-tailscale 로그인 후 다시 확인}"
  echo " 포트: 2000"
  echo "=========================================="
fi
