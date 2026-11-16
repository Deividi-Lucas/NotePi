# Homelab k3s no Raspberry Pi 4 + NotePi como primeiro app — Especificação de design

**Data:** 2026-11-16
**Autor:** Deividi-Lucas
**Status:** design aprovado em 3 partes; aguardando revisão deste documento
**Relacionado:** `docs/superpowers/specs/2026-11-10-notepi-design.md` (o app)

## 1. Objetivo

Transformar um Raspberry Pi 4 (4 ou 8 GB, cartão SD) num cluster **k3s de um nó**, gerido por **GitOps com Argo CD**,
para rodar vários serviços pessoais. O NotePi é o primeiro serviço.

### Critérios de sucesso

- Um push na `main` do NotePi chega ao Pi sozinho (CI → imagem → commit no homelab → Argo CD), sem comando manual.
- Cada serviço tem um endereço `https://<app>.<tailnet>.ts.net`, acessível só pela tailnet do usuário.
- Nenhum segredo em texto puro em repositório público.
- Se o cartão SD morrer: cartão novo + `bootstrap` + chave do Sealed Secrets restaurada → o cluster volta igual; os
  dados de cada app voltam pelo backup dele.
- A plataforma (k3s + Argo CD + operador do Tailscale + Sealed Secrets) usa no máximo ~1,1 GB de RAM.

### Fora do escopo

Vários nós, alta disponibilidade, monitoramento (Prometheus/Grafana), acesso pela internet aberta, Argo CD Image
Updater, migração para SSD (decisão do usuário: só cartão SD, com cuidados).

## 2. Decisões

| Tema | Decisão | Motivo |
|---|---|---|
| Orquestração | k3s, 1 nó | Leve, feito para ARM |
| Deploy | GitOps com Argo CD (padrão "app de apps") | Escolha do usuário; painel web; histórico no Git |
| Repositórios | `homelab` central (cluster + manifestos de todos os apps); cada app guarda só código, Dockerfile e CI | Visão única do que roda no Pi |
| Nova versão de um app | A CI do app faz commit no `homelab` trocando a imagem | Tudo no Git; sem componente extra no cluster |
| Acesso externo | Operador do Tailscale para Kubernetes, um Ingress HTTPS por app | Nada exposto na internet; HTTPS automático |
| Segredos | Sealed Secrets | Segredo criptografado no Git público; ~30 MB de RAM |
| Armazenamento | `local-path` do k3s no cartão SD | Decisão do usuário; mitigado pelos cuidados abaixo |
| Manifestos | Kustomize | Nativo no Argo CD; `kustomize edit set image` na CI |
| Imagens | GHCR público (`ghcr.io/deividi-lucas/<app>`), arm64 + amd64 | O cluster baixa sem senha |
| Descartados | Flux (sem painel), kubectl manual (sem GitOps), Image Updater (mais RAM), Traefik/Cloudflare (exposição pública) | |

## 3. Arquitetura

```
GitHub
 ├─ NotePi ── Actions: testes → build arm64/amd64 → Trivy → GHCR
 │                                   └─ commit "notepi: <tag>" ─┐
 └─ homelab (fonte da verdade) ◄────────────────────────────────┘
        ▲ Argo CD acompanha por pull (nenhuma porta aberta)
Raspberry Pi 4 ─ k3s (sem Traefik/ServiceLB)
 ├─ argocd          → https://argocd.<tailnet>.ts.net
 ├─ sealed-secrets
 ├─ tailscale       (operador + proxies de Ingress)
 └─ notepi          Deployment (1 réplica, Recreate) + PVC local-path
                    + CronJob 03:00 (backup → pendrive + rclone crypt)
```

### Repositório `homelab` (novo, público)

```
homelab/
├─ bootstrap/
│  ├─ instalar-k3s.sh          # uma vez por Pi: cuidados com o SD, cgroups, k3s, Argo CD, app raiz
│  └─ argocd-values.yaml       # Argo CD enxuto
├─ platform/
│  ├─ sealed-secrets.yaml      # Application (Helm), sync-wave 1
│  └─ tailscale-operator.yaml  # Application (Helm) + SealedSecret OAuth, sync-wave 2
├─ apps/
│  ├─ root.yaml                # Application que instala platform/ e apps/*
│  └─ notepi/                  # Kustomize (sync-wave 3)
│     ├─ kustomization.yaml
│     ├─ namespace.yaml
│     ├─ configmap.yaml
│     ├─ pvc.yaml
│     ├─ deployment.yaml
│     ├─ service.yaml
│     ├─ ingress.yaml
│     ├─ networkpolicy.yaml
│     ├─ cronjob-backup.yaml
│     └─ sealedsecret-rclone.yaml
└─ README.md                   # instalação, segredos, recuperação
```

O nome real do tailnet **não** é escrito no repositório; o Ingress usa só o nome curto (`notepi`) e o operador
completa com o domínio da tailnet.

## 4. Plataforma

### 4.1 Bootstrap (`bootstrap/instalar-k3s.sh`, idempotente)

1. Cuidados com o cartão SD: journald só na RAM (`Storage=volatile`), swap em zram (desliga dphys-swapfile; mantém
   `rpi-swap` se existir), `noatime` com cópia do fstab (`.bak`).
2. Habilita cgroups de memória: acrescenta `cgroup_enable=memory cgroup_memory=1` em `/boot/firmware/cmdline.txt`
   (ou `/boot/cmdline.txt`), uma única vez; avisa que precisa reiniciar e para se ainda não reiniciou.
3. Instala o k3s com versão fixa (`INSTALL_K3S_VERSION`) e:
   `--disable traefik --disable servicelb --write-kubeconfig-mode 600`,
   `--kubelet-arg container-log-max-size=5Mi --kubelet-arg container-log-max-files=2`,
   `--kubelet-arg image-gc-high-threshold=80 --kubelet-arg image-gc-low-threshold=60`.
4. Instala o Argo CD por Helm com versão de chart fixa e `argocd-values.yaml`:
   sem Dex, sem notifications, sem ApplicationSet; limites de memória (server 128Mi, repo-server 256Mi,
   application-controller 256Mi, redis 64Mi).
5. Aplica `apps/root.yaml`. Daqui em diante tudo vem do Git.

### 4.2 Componentes (instalados pelo Argo CD, em ordem por `argocd.argoproj.io/sync-wave`)

| Wave | Componente | Detalhe |
|---|---|---|
| 1 | Sealed Secrets (Helm, versão fixa) | Namespace `kube-system`; `kubeseal` no PC do usuário |
| 2 | Operador do Tailscale (Helm, versão fixa) | OAuth client com `tag:k8s-operator`; proxies com `tag:k8s`; o segredo OAuth vem de um SealedSecret |
| 3 | Apps | Um namespace por app |

### 4.3 Segredos

| Segredo | Onde fica | Como é criado |
|---|---|---|
| OAuth do operador do Tailscale | SealedSecret em `platform/` | Painel do Tailscale → `kubeseal` no PC |
| `rclone.conf` (remote `gdrive` com `drive.file` + `cofre` crypt) | SealedSecret em `apps/notepi/` | `rclone config` no PC → `kubeseal` |
| Token do GitHub que atualiza o homelab | Secret do GitHub Actions no repo do app | PAT *fine-grained*: só `homelab`, `contents: write` |
| Chave privada do Sealed Secrets | Fora do Git: gerenciador de senhas do usuário | `kubectl get secret -n kube-system -l sealedsecrets.bitnami.com/sealed-secrets-key -o yaml` uma vez |

### 4.4 Acesso e rede

- ACL do Tailscale: só o usuário acessa `tag:k8s:443`; `tagOwners` para `tag:k8s-operator` e `tag:k8s`.
- Argo CD: Ingress do Tailscale (`argocd`), senha inicial trocada no primeiro acesso e o segredo inicial apagado.
- NetworkPolicy padrão por app: entrada só do namespace `tailscale`; saída negada (exceto DNS quando o app precisar).
- Padrão de pod para todos os apps: `runAsNonRoot`, uid fixo, `readOnlyRootFilesystem`,
  `allowPrivilegeEscalation: false`, `capabilities.drop: [ALL]`, `seccompProfile: RuntimeDefault`, limites de memória.

### 4.5 Recuperação

Cartão novo → Raspberry Pi OS Lite 64-bit → `bootstrap/instalar-k3s.sh` → restaurar a chave do Sealed Secrets
(`kubectl apply` antes do Argo sincronizar) → Argo CD recria tudo → restaurar dados de cada app (NotePi: copiar
`notas-AAAA-MM-DD.db` do pendrive ou de `cofre:backup` para o volume, com o app parado).

## 5. NotePi no cluster

### 5.1 Imagem (`Dockerfile` no repo do NotePi)

- Duas etapas, base `python:3.12-slim` fixada por digest.
- Etapa de build: `pip install --require-hashes -r requirements.lock` num venv; depois `pip install --no-deps .`.
- Etapa final: copia o venv; usuário uid/gid 10001; `PYTHONDONTWRITEBYTECODE=1`, `PYTHONUNBUFFERED=1`;
  `EXPOSE 8000`; `CMD ["uvicorn", "notepi.app:app", "--host", "0.0.0.0", "--port", "8000", "--workers", "1",
  "--limit-concurrency", "20"]`.
- `.dockerignore`: `.git`, `.venv`, `dados*`, `.superpowers`, `tests`, `docs`, `build`.

### 5.2 Manifestos (`homelab/apps/notepi/`)

- **ConfigMap:** `NOTEPI_DB=/dados/notas.db`, `NOTEPI_BACKUP_DIR=/backup`, `NOTEPI_BACKUP_EXIGIR_MONTAGEM=0`,
  `NOTEPI_BACKUP_MARCADOR=1`, `NOTEPI_HOSTS=notepi.<tailnet>.ts.net` (o usuário escreve o nome completo no ConfigMap
  na instalação; ver §8.2), `NOTEPI_USUARIOS=` (vazio até a verificação da §8.1).
- **PVC:** `local-path`, `ReadWriteOnce`, 2Gi, montado em `/dados`.
- **Deployment:** `replicas: 1`, `strategy: Recreate`; volumes: PVC em `/dados`, `hostPath /mnt/backup`
  (`type: Directory`, `readOnly: true`) em `/backup`, `emptyDir` (`medium: Memory`, 64Mi) em `/tmp`;
  `resources.limits.memory: 256Mi`, `requests: 64Mi/50m`; `livenessProbe` e `readinessProbe` por `tcpSocket :8000`;
  `securityContext` do padrão da §4.4.
- **Service:** `ClusterIP`, porta 80 → 8000.
- **Ingress:** `ingressClassName: tailscale`, `tls.hosts: [notepi]`.
- **NetworkPolicy:** entrada só do namespace `tailscale` na porta 8000; saída negada para o pod web; para o pod do
  CronJob, saída liberada para DNS e 443 (rclone).

### 5.3 Backup (`CronJob`)

- `schedule: "0 3 * * *"`, `timeZone: America/Sao_Paulo`, `concurrencyPolicy: Forbid`,
  `successfulJobsHistoryLimit: 3`, `failedJobsHistoryLimit: 3`.
- `initContainer` com a imagem do NotePi: `python -m notepi.manutencao` (lixeira, backup no pendrive, rotação de 30 dias).
  Monta o PVC em `/dados` e `hostPath /mnt/backup` (leitura e escrita) em `/backup`.
- Container principal com a imagem oficial `rclone/rclone` (versão fixa por digest):
  `rclone copy /backup cofre:backup --include "notas-*.db" --max-age 48h --config /config/rclone.conf`.
  O `rclone.conf` vem do SealedSecret, montado só nesse container.
- O PVC é `ReadWriteOnce`; como há um nó só, o pod do CronJob e o do app montam o mesmo volume.

### 5.4 Mudança no app: marcador do pendrive

Dentro do container, `/backup` é sempre um ponto de montagem (o `hostPath`), então `os.path.ismount` não detecta o
pendrive ausente. Nova opção:

- `NOTEPI_BACKUP_MARCADOR=1` → `manutencao.executar` exige o arquivo `<backup_dir>/.notepi-pendrive`; sem ele, falha com
  "pendrive de backup ausente (arquivo .notepi-pendrive não encontrado)".
- `/saude` usa a mesma regra para mostrar o aviso "Pendrive de backup não está montado".
- O README explica criar o arquivo uma vez: `sudo touch /mnt/backup/.notepi-pendrive` com o pendrive montado.
- `NOTEPI_BACKUP_EXIGIR_MONTAGEM` continua valendo para a instalação com systemd.

### 5.5 CI (`.github/workflows/` no repo do NotePi)

- `testes.yml` — em `pull_request` e `push`: Python 3.12, `pip install --require-hashes -r requirements.lock`,
  `pip install --no-deps -e .`, pytest. Sem segredos. `permissions: contents: read`.
- `publicar.yml` — em `push` na `main`, depois dos testes:
  1. QEMU + Buildx; build `linux/arm64,linux/amd64`;
  2. Trivy na imagem: falha com vulnerabilidade `CRITICAL` corrigível;
  3. push para `ghcr.io/deividi-lucas/notepi:sha-<7>` (`permissions: packages: write`);
  4. checkout do `homelab` com o PAT (`secrets.HOMELAB_TOKEN`), `kustomize edit set image
     ghcr.io/deividi-lucas/notepi=ghcr.io/deividi-lucas/notepi:sha-<7>@<digest>` em `apps/notepi/`, commit
     "notepi: sha-<7>" e push.
- Todas as Actions fixadas por SHA; nunca `pull_request_target`; `concurrency` para não publicar duas vezes em paralelo.
- O pacote do GHCR fica público (o repositório é público).

## 6. Erros e casos especiais

| Situação | Comportamento |
|---|---|
| Pendrive ausente na hora do backup | `initContainer` falha (marcador ausente) → Job falha → `/saude` mostra "atrasado" e "pendrive ausente" |
| Nuvem fora do ar | Só o container do rclone falha; o backup no pendrive já foi feito |
| Imagem com vulnerabilidade crítica | CI falha antes de publicar; o homelab não muda |
| Commit no homelab falha (token expirado) | CI falha com mensagem clara; a imagem existe mas não é usada até o próximo push |
| Argo CD não consegue sincronizar | O app continua na versão anterior; o painel mostra o erro |
| Cartão SD morre | Procedimento da §4.5 |
| Pod reiniciado durante gravação | SQLite em WAL; no máximo a última transação se perde |

## 7. Testes e verificação

- **NotePi:** testes de `NOTEPI_BACKUP_MARCADOR` (sem marcador → falha; com marcador → backup; `/saude` mostra o aviso);
  a suíte toda continua passando.
- **Imagem:** `docker build` local + `docker run` com `NOTEPI_HOSTS=localhost` → `GET /` 200; a imagem roda como uid 10001;
  o sistema de arquivos só leitura não quebra (`--read-only --tmpfs /tmp`).
- **Manifestos:** `kustomize build apps/notepi` e `kubeconform` na CI do homelab (workflow simples, sem segredos).
- **No Pi (manual, roteiro no README):** `kubectl get pods -A` tudo Running; abrir `https://notepi.<tailnet>.ts.net`;
  criar uma nota; `kubectl create job --from=cronjob/notepi-backup teste -n notepi` e conferir o arquivo no pendrive e
  em `cofre:backup`; fazer um push no NotePi e ver a versão nova chegar sozinha; conferir no painel do Argo CD.
- **Verificação de memória:** `kubectl top pods -A` (metrics-server do k3s) — plataforma ≤ ~1,1 GB.

## 8. Pontos a confirmar na instalação

1. **Cabeçalho `Tailscale-User-Login` no Ingress do operador.** Se o proxy do operador enviar o cabeçalho, preencher
   `NOTEPI_USUARIOS`. Se não enviar, deixar vazio e depender só da ACL. Verificação: uma rota de teste temporária ou
   `kubectl logs` com log do cabeçalho — sem alterar o código do app.
2. **Nome do tailnet no `NOTEPI_HOSTS`.** Decisão: o usuário coloca o nome completo no ConfigMap, versionado (o nome
   do tailnet já é público nos registros de certificados, então isso é aceitável). Esta é a única exceção à regra da
   §3 de não escrever o nome do tailnet no repositório.
3. **Versões fixas** (k3s, chart do Argo CD, chart do Sealed Secrets, chart do operador do Tailscale, imagem do rclone,
   digest do `python:3.12-slim`): escolhidas na implementação, as mais recentes estáveis naquele dia, e registradas no
   README do homelab.
