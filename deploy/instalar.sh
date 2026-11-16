#!/usr/bin/env bash
# Instala ou atualiza o NotePi num Raspberry Pi (Raspberry Pi OS Lite 64-bit).
# Rode a partir da pasta do projeto copiada para o Pi:
#   sudo ./deploy/instalar.sh
# Pode rodar de novo quantas vezes quiser (por exemplo, para atualizar o código).
set -euo pipefail

[ "$(id -u)" -eq 0 ] || { echo "Rode com sudo: sudo ./deploy/instalar.sh"; exit 1; }
ORIGEM="$(cd "$(dirname "$0")/.." && pwd)"

echo "==> Pacotes do sistema"
apt-get update
apt-get install -y python3-venv sqlite3 rclone rsync curl

echo "==> Usuário 'notepi' e pastas"
id notepi >/dev/null 2>&1 || useradd --system --home-dir /var/lib/notepi --create-home --shell /usr/sbin/nologin notepi
install -d -o notepi -g notepi -m 750 /var/lib/notepi
install -d -m 755 /opt/notepi
[ -d /mnt/backup ] || mkdir -m 700 /mnt/backup

echo "==> Código e dependências Python"
rsync -a --delete --chown=root:root --exclude .git --exclude .venv --exclude 'dados*' --exclude __pycache__ "$ORIGEM/" /opt/notepi/app/
[ -d /opt/notepi/venv ] || python3 -m venv /opt/notepi/venv
/opt/notepi/venv/bin/pip install --upgrade pip
/opt/notepi/venv/bin/pip install --require-hashes -r /opt/notepi/app/requirements.lock
/opt/notepi/venv/bin/pip install --no-deps /opt/notepi/app

echo "==> Configuração"
if [ ! -f /etc/notepi.env ]; then
  install -m 640 -o root -g notepi "$ORIGEM/deploy/notepi.env.exemplo" /etc/notepi.env
fi

echo "==> Cuidados com o cartão SD"
# 1) Logs do sistema só na memória RAM (somem ao reiniciar, mas não gastam o cartão)
install -d /etc/systemd/journald.conf.d
printf '[Journal]\nStorage=volatile\nRuntimeMaxUse=30M\n' > /etc/systemd/journald.conf.d/notepi.conf
systemctl restart systemd-journald
# 2) Swap na RAM comprimida (zram) em vez de arquivo de swap no cartão
if command -v dphys-swapfile >/dev/null 2>&1; then
  dphys-swapfile swapoff || true
  systemctl disable --now dphys-swapfile || true
fi
if dpkg -s rpi-swap >/dev/null 2>&1; then
  echo "    rpi-swap já cuida do zram neste sistema"
else
  apt-get install -y zram-tools
  printf 'ALGO=lz4\nPERCENT=50\n' > /etc/default/zramswap
  systemctl enable --now zramswap || true
fi
# 3) noatime na partição raiz (o Raspberry Pi OS normalmente já vem assim)
sed -i.bak -E '/[[:space:]]\/[[:space:]]+ext4[[:space:]]/ { /noatime/! s/(ext4[[:space:]]+)([^[:space:]]+)/\1\2,noatime/ }' /etc/fstab

echo "==> Serviços"
install -m 644 "$ORIGEM/deploy/notepi.service" "$ORIGEM/deploy/notepi-manutencao.service" \
  "$ORIGEM/deploy/notepi-manutencao.timer" /etc/systemd/system/
systemctl daemon-reload
systemctl enable notepi.service notepi-manutencao.timer
systemctl restart notepi.service
systemctl start notepi-manutencao.timer

echo "==> Tailscale (acesso de qualquer lugar)"
command -v tailscale >/dev/null 2>&1 || curl -fsSL https://tailscale.com/install.sh | sh
tailscale status >/dev/null 2>&1 || tailscale up
tailscale serve --bg 8000

ENDERECO="$(tailscale status --json | python3 -c 'import json,sys; print(json.load(sys.stdin)["Self"]["DNSName"].rstrip("."))')"
echo "==> Hosts permitidos"
if [ -z "$ENDERECO" ]; then
  echo "AVISO: sem nome do Tailscale (MagicDNS desligado?). NOTEPI_HOSTS em /etc/notepi.env não foi alterado."
elif ! grep -E '^NOTEPI_HOSTS=' /etc/notepi.env | grep -qF "$ENDERECO"; then
  if grep -qE '^NOTEPI_HOSTS=' /etc/notepi.env; then
    sed -i.bak -E "s|^NOTEPI_HOSTS=.*|NOTEPI_HOSTS=$ENDERECO,127.0.0.1,localhost|" /etc/notepi.env
  else
    echo "NOTEPI_HOSTS=$ENDERECO,127.0.0.1,localhost" >> /etc/notepi.env
  fi
  systemctl restart notepi.service
fi

echo
echo "Pronto! Abra no celular ou no PC (com o Tailscale ligado): https://$ENDERECO"
echo "Saúde do sistema: https://$ENDERECO/saude"
