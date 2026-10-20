#!/bin/bash
# 나만의리니지 서버 업데이트 (캐릭터·설정 유지). 사용: curl ... update.sh | REPO_RAW=... bash
set -e
APP=/opt/lineage; DB=l1jdb_kr
REPO_RAW=${REPO_RAW:-https://raw.githubusercontent.com/insjung0601-lgtm/lineage-vps/main}
cd $APP
STAMP=$(date +%Y%m%d_%H%M%S)
mkdir -p backups/jar
cp linfree.jar backups/jar/linfree_$STAMP.jar
echo "기존 서버 파일 백업: $APP/backups/jar/linfree_$STAMP.jar"
curl -fsSL -o linfree.jar.new "$REPO_RAW/files/linfree.jar" && mv linfree.jar.new linfree.jar
for f in manager.py index.html; do curl -fsSL -o manager/$f "$REPO_RAW/files/manager/$f"; done
[ -f config/solo.properties ] || curl -fsSL -o config/solo.properties "$REPO_RAW/files/config/solo.properties"
mkdir -p sql
for f in 04_solo_items.sql; do curl -fsSL -o sql/$f "$REPO_RAW/files/sql/$f"; mysql -uroot --default-character-set=utf8 $DB < sql/$f; done
md5sum linfree.jar
systemctl restart lineage lineage-manager
echo "=========================================="
echo " 업데이트 완료 - 1~2분 뒤 접속하세요"
echo " 되돌리기: cp $APP/backups/jar/linfree_$STAMP.jar $APP/linfree.jar && systemctl restart lineage"
echo "=========================================="
