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
Confirme antes que as últimas alterações estão commitadas: o `git archive` empacota o último commit.
No PC (PowerShell), dentro da pasta do projeto:
```powershell
git archive -o notepi.tar.gz HEAD
scp notepi.tar.gz <seu-usuario>@notepi.local:~/
```
Isso envia só os arquivos do projeto que estão no git (sem `.venv`, sem os dados locais) e mantém a
permissão de execução do script.

### 3. Preparar o Tailscale
Crie uma conta gratuita em **tailscale.com** e instale o app do Tailscale no celular e no PC, sempre
com a mesma conta. No painel de administração do Tailscale (página **DNS**), ative **MagicDNS** e
**HTTPS Certificates** **antes** de rodar o script de instalação. Sem isso, o `tailscale serve` pode
travar ou falhar.

### 4. Instalar
```bash
ssh <seu-usuario>@notepi.local
mkdir -p ~/NotePi && tar -xzf ~/notepi.tar.gz -C ~/NotePi
cd ~/NotePi
sudo bash deploy/instalar.sh
```
O script instala tudo, liga o app e o backup diário, e configura o Tailscale. Na primeira vez ele
mostra um link para você entrar na sua conta Tailscale.

### 5. Pendrive de backup
Formate o pendrive como ext4 (ou use vfat) e descubra o UUID com `lsblk -f`. Adicione ao `/etc/fstab`:
```
# ext4:
UUID=<uuid>  /mnt/backup  ext4  defaults,noatime,nofail  0  2
# ou vfat:
UUID=<uuid>  /mnt/backup  vfat  defaults,nofail,uid=notepi,gid=notepi,umask=077  0  0
```
Depois: `sudo systemctl daemon-reload` e `sudo mount -a`. Se for ext4, rode também `sudo chown notepi:notepi /mnt/backup`.

### 6. Cópia na nuvem (opcional, recomendado)
No PC, instale o rclone (https://rclone.org/downloads/) e rode:
```powershell
rclone authorize "drive" --drive-scope drive.file
```
Ele abre o navegador para você entrar na conta Google e imprime um token. Copie esse token. O escopo `drive.file`
dá ao rclone acesso só aos arquivos que ele mesmo criar, não ao seu Drive inteiro.

No Pi, crie o remote (o Pi não tem tela, por isso o token vem do PC):
```bash
sudo -u notepi -H rclone config
```
Crie um remote chamado `gdrive` do tipo `drive`. Na pergunta de **scope**, escolha `drive.file`. Quando perguntar
**"Use web browser to automatically authenticate?"**, responda **n** e cole o token.

Depois crie, na mesma sessão do `rclone config`, um segundo remote chamado `cofre`, do tipo `crypt`, apontando para
`gdrive:NotePi`. Defina uma senha forte (e a senha 2 / salt, se quiser) e **guarde-a fora do Pi**, por exemplo num
gerenciador de senhas: sem ela os backups da nuvem não podem ser lidos. Assim, o token guardado no Pi e os arquivos
no Drive ficam inúteis para quem não tiver a senha.

Depois aponte o destino e teste:
```bash
sudo nano /etc/notepi.env           # NOTEPI_RCLONE_DESTINO=cofre:backup
sudo systemctl start notepi-manutencao.service   # testa agora
sudo -u notepi -H rclone ls cofre:backup         # deve listar notas-AAAA-MM-DD.db de hoje
```
Se não aparecer nada, veja `journalctl -u notepi-manutencao -n 30`.

A nuvem guarda todos os backups (não apaga os antigos). Limpe-a manualmente de vez em quando, se quiser.

### 7. Imagem do cartão
Com tudo funcionando, desligue (`sudo shutdown now`), coloque o cartão no PC e salve uma imagem
dele (Win32 Disk Imager, opção "Read"). Se o cartão estragar, grave essa imagem num cartão novo e
restaure o último backup (abaixo).

## Quem pode acessar
Por padrão, qualquer aparelho da sua tailnet que alcance o Pi abre o app. Há duas camadas para restringir isso.

**1. ACL no painel do Tailscale (Access controls).** Marque o Pi com uma tag e libere só o seu usuário na porta 443.
No Pi: `sudo tailscale up --advertise-tags=tag:notepi`. No painel, em **Access controls**, use algo como (troque o e-mail pelo seu login):
```json
{
  "tagOwners": { "tag:notepi": ["voce@example.com"] },
  "grants": [
    { "src": ["voce@example.com"], "dst": ["tag:notepi"], "ip": ["tcp:443"] }
  ]
}
```
Se a sua tailnet ainda usa `acls`, o equivalente é `{"action": "accept", "src": ["voce@example.com"], "dst": ["tag:notepi:443"]}`.
Cuidado para não tirar o seu próprio acesso (SSH ao Pi, por exemplo) ao trocar a política.

**2. Lista de usuários no app.** Em `/etc/notepi.env`, preencha com o seu login do Tailscale (vários, separados por vírgula):
```
NOTEPI_USUARIOS=voce@example.com
```
e rode `sudo systemctl restart notepi`. Com a lista preenchida, o app recusa (403) qualquer pedido sem o cabeçalho
`Tailscale-User-Login` com um desses valores. Vazia = desligado.

Atenção: esse cabeçalho só é confiável enquanto o uvicorn escuta em `127.0.0.1` atrás do `tailscale serve`, que o
preenche e descarta o que vier do cliente. Se expuser a porta 8000 de outro jeito, qualquer um poderia forjá-lo.

## Atualizar o código no Pi
Faça o passo 2 de novo (novo `git archive`, `scp` e `tar` por cima de `~/NotePi`) e depois:
```bash
cd ~/NotePi && sudo bash deploy/instalar.sh
```

## Restaurar um backup
```bash
sudo systemctl stop notepi
sudo cp /mnt/backup/notas-AAAA-MM-DD.db /var/lib/notepi/notas.db
sudo rm -f /var/lib/notepi/notas.db-wal /var/lib/notepi/notas.db-shm
sudo chown notepi:notepi /var/lib/notepi/notas.db
sudo systemctl start notepi
```
Se o pendrive for perdido, baixe o backup da nuvem antes e use o arquivo baixado no lugar de `/mnt/backup/...`:
```bash
sudo -u notepi -H rclone copy cofre:backup/notas-AAAA-MM-DD.db /tmp/
sudo cp /tmp/notas-AAAA-MM-DD.db /var/lib/notepi/notas.db
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
