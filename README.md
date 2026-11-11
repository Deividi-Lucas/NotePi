# NotePi

Anotações pessoais (cultos, estudos, guias de requisitos) com conexões entre Bíblia, tecnologia,
finanças, casa/obra, pintura e conhecimentos gerais. Roda num Raspberry Pi em casa e é acessado
pelo navegador de qualquer aparelho, através do Tailscale.

Especificação: `docs/superpowers/specs/2026-11-10-notepi-design.md`

## Desenvolver no PC (Windows)

```powershell
python -m venv .venv
.venv\Scripts\python -m pip install -e ".[dev]"
.venv\Scripts\python -m pytest
.venv\Scripts\python -m uvicorn notepi.app:app --reload
```

Abra http://127.0.0.1:8000. Os dados de desenvolvimento ficam na pasta `dados/` (fora do git).

## Instalar no Raspberry Pi 3B

### 1. Preparar o cartão SD
- Use um cartão de **alta durabilidade** (SanDisk High Endurance, Samsung PRO Endurance ou A1/A2 de marca), 32 GB ou mais.
- No **Raspberry Pi Imager**, grave o **Raspberry Pi OS Lite (64-bit)**. Na engrenagem de opções: defina o nome `notepi`, usuário e senha, Wi-Fi (se não usar cabo), **ative o SSH** e escolha o fuso `America/Sao_Paulo`.
- Use a **fonte oficial 5V/2,5A**. Um nobreak pequeno é recomendado.

### 2. Copiar o projeto para o Pi
No PC (PowerShell), dentro da pasta do projeto:
```powershell
scp -r . <seu-usuario>@notepi.local:~/NotePi
```

### 3. Instalar
```bash
ssh <seu-usuario>@notepi.local
cd ~/NotePi
sudo ./deploy/instalar.sh
```
O script instala tudo, liga o app e o backup diário, e configura o Tailscale. Na primeira vez ele
mostra um link para você entrar na sua conta Tailscale. No painel do Tailscale, ative **MagicDNS** e
**HTTPS Certificates**. Instale o app do Tailscale no celular e no PC, com a mesma conta.

### 4. Pendrive de backup
Formate o pendrive como ext4 (ou use vfat) e descubra o UUID com `lsblk -f`. Adicione ao `/etc/fstab`:
```
# ext4:
UUID=<uuid>  /mnt/backup  ext4  defaults,noatime,nofail  0  2
# ou vfat:
UUID=<uuid>  /mnt/backup  vfat  defaults,nofail,uid=notepi,gid=notepi,umask=077  0  0
```
Depois: `sudo mount -a`. Se for ext4, rode também `sudo chown notepi:notepi /mnt/backup`.

### 5. Cópia na nuvem (opcional, recomendado)
```bash
sudo -u notepi rclone config        # crie um remote, por exemplo "gdrive"
sudo nano /etc/notepi.env           # NOTEPI_RCLONE_DESTINO=gdrive:NotePi/backup
sudo systemctl start notepi-manutencao.service   # testa agora
```

### 6. Imagem do cartão
Com tudo funcionando, desligue (`sudo shutdown now`), coloque o cartão no PC e salve uma imagem
dele (Win32 Disk Imager, opção "Read"). Se o cartão estragar, grave essa imagem num cartão novo e
restaure o último backup (abaixo).

## Atualizar o código no Pi
Copie a pasta de novo (passo 2) e rode `sudo ./deploy/instalar.sh` outra vez.

## Restaurar um backup
```bash
sudo systemctl stop notepi
sudo cp /mnt/backup/notas-AAAA-MM-DD.db /var/lib/notepi/notas.db
sudo rm -f /var/lib/notepi/notas.db-wal /var/lib/notepi/notas.db-shm
sudo chown notepi:notepi /var/lib/notepi/notas.db
sudo systemctl start notepi
```

## Comandos úteis
- Ver se está rodando: `systemctl status notepi`
- Ver erros: `journalctl -u notepi -n 50`
- Rodar o backup agora: `sudo systemctl start notepi-manutencao.service`
- Desligar com segurança: `sudo shutdown now` (nunca puxe da tomada)

## Dicas de uso
- Versículos escritos no texto ("Jo 3:16", "Rm 12:1-2", "Sl 23") viram tags sozinhos.
- "Jó" com acento é o livro de Jó; "Jo" sem acento é João.
- No campo de tags, separe por vírgula. Para um versículo como tag, use hífen: `Rm 12:1-2`.
- Exportar tudo em Markdown: página **/saude**, botão **Exportar**.
