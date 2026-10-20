# lineage-vps

1인용 L1J-KR 3.80 서버를 Ubuntu 24.04 VPS에 설치하는 스크립트.

```
curl -fsSL https://raw.githubusercontent.com/insjung0601-lgtm/lineage-vps/main/install.sh | bash
```

- 서버 소스: https://github.com/hillpath/L1J-KR_3.80 (설치 시 내려받음)
- `files/` : 1인용 설정, 패치된 linfree.jar(고인챈트·AC 표시 패치 v4), 보스 리스폰·변신 한글화 SQL
- 게임 포트(2000)는 Tailscale 네트워크 안에서만 열림

웹 매니저: http://<tailscale IP>:8080 (비밀번호: /opt/lineage/manager/password.txt)

서버 관리
```
systemctl status lineage     # 상태
systemctl restart lineage    # 재시작
tail -f /opt/lineage/log/console.log
```
