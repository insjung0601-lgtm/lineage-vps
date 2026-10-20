-- 나만의리니지: 1인 플레이용 DB 조정
-- 롤백은 sql/99_rollback_tuning.sql

-- 1) 보스 스폰 원본 백업 (최초 1회만 생성되고 이후에는 덮어쓰지 않음)
CREATE TABLE IF NOT EXISTS solo_backup_spawnlist_boss AS SELECT * FROM spawnlist_boss;

-- 2) 모든 보스를 20분 주기 리스폰으로 변경 (BossCycle.xml의 SOLO20)
UPDATE spawnlist_boss SET cycle_type = 'SOLO20';

-- 3) GM 명령어는 기본으로 GM 등급(5842)에서만 동작하므로 변경 없음
