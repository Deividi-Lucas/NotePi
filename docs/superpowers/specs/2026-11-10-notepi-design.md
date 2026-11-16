# NotePi — Especificação de design

**Data:** 2026-11-10
**Autor:** Deividi-Lucas
**Status:** design aprovado em partes; aguardando revisão deste documento

## 1. Objetivo

O NotePi é um app web pessoal, hospedado num Raspberry Pi em casa e acessível pelo navegador de qualquer dispositivo. Ele serve para registrar anotações e cruzar o conhecimento entre áreas: Bíblia (cultos, estudos, hermenêutica, exegese), tecnologia, finanças, casa/obra (elétrica, ar-condicionado, construção), pintura e conhecimentos gerais.

O valor do app está nas **conexões entre notas**: encontrar, por exemplo, todas as notas de qualquer área que citam Romanos 12, ou rever o guia "o que olhar antes de comprar um pincel" quando for comprar de novo.

### Critérios de sucesso

- Criar uma nota de culto pelo celular em menos de 10 segundos (do app aberto até começar a digitar).
- Nenhum texto digitado se perde por queda de conexão.
- Uma busca por palavra ou versículo retorna resultados relevantes em menos de 1 segundo no Pi 3B.
- Os dados podem ser exportados em Markdown a qualquer momento.

### Fora da versão 1

Links manuais entre notas (`[[nota]]`), sugestões de conexão por IA, texto bíblico embutido, modo offline completo (só o rascunho local está na v1), login dentro do app, múltiplos usuários.

## 2. Decisões

| Tema | Decisão | Motivo |
|---|---|---|
| Cruzamento | Busca de texto completo + tags | Simples, barato e roda bem no Pi; IA pode vir depois |
| Hospedagem | Raspberry Pi 3B com cartão SD, em casa | Dados ficam com o usuário, sem custo mensal |
| Acesso externo | Tailscale | Sem abrir portas no roteador; serve como controle de acesso e fornece HTTPS |
| Formato | Markdown livre + modelos | Escrever rápido no culto, com estrutura quando ajuda |
| Bíblia | Referências detectadas viram tags | Cruzar notas por trecho bíblico sem precisar de licença de tradução |
| Stack | Python 3.11 + FastAPI + SQLite (FTS5) + Jinja2 + HTMX | Leve para 1 GB de RAM; o banco é um arquivo só; pouco JavaScript |
| Alternativas descartadas | SilverBullet, Trilium Notes | O usuário quer código próprio e o recurso de versículos sob medida |

## 3. Arquitetura

```
Celular / PC (navegador)
        │  Tailscale (HTTPS via `tailscale serve`)
        ▼
Raspberry Pi 3B — Raspberry Pi OS Lite 64-bit
  ├─ systemd: notepi.service → Uvicorn (1 worker) → FastAPI
  │     ├─ rotas HTML (Jinja2 + HTMX)
  │     └─ serviços: notas, tags, versículos, busca, backup
  └─ /var/lib/notepi/notas.db  (SQLite, modo WAL)
```

### Unidades do código

Cada módulo tem uma responsabilidade e pode ser testado sozinho.

| Módulo | Responsabilidade | Depende de |
|---|---|---|
| `notepi/config.py` | Lê a configuração das variáveis de ambiente (`NOTEPI_DB`, `NOTEPI_BACKUP_DIR`…) | nada |
| `notepi/texto.py` | `remover_acentos`, `slug` | nada |
| `notepi/db.py` | Conexão, PRAGMAs (WAL, foreign keys), migrações | sqlite3 |
| `notepi/versiculos.py` | Encontrar referências bíblicas num texto e normalizá-las | nada (função pura) |
| `notepi/livros.py` | Tabela dos 66 livros: nome, abreviações em PT-BR e número de capítulos | nada |
| `notepi/notas.py` | Criar, ler, editar, mover para a lixeira e restaurar notas | db, tags |
| `notepi/tags.py` | Tags livres e de versículo; sincronizar as tags de uma nota | db, versiculos |
| `notepi/busca.py` | Busca FTS5 com filtros; notas relacionadas | db |
| `notepi/backup.py` | Backup online do SQLite, rotação de 30 dias, exportação em Markdown | db |
| `notepi/manutencao.py` | Tarefa diária: esvaziar a lixeira antiga, backup e rotação | notas, backup |
| `notepi/modelos/` | Modelos em Markdown e a função que os carrega | nada |
| `notepi/web/` | Rotas FastAPI, templates e arquivos estáticos | todos acima |
| `deploy/` | `instalar.sh`, `notepi.service`, `backup.timer` | — |

## 4. Modelo de dados

```sql
CREATE TABLE notas (
  id            INTEGER PRIMARY KEY,
  titulo        TEXT NOT NULL,
  conteudo      TEXT NOT NULL DEFAULT '',      -- Markdown
  area          TEXT NOT NULL CHECK (area IN
                ('biblia','tecnologia','financas','casa_obra','pintura','geral')),
  modelo        TEXT,                           -- 'culto' | 'guia_requisitos' | NULL
  criada_em     TEXT NOT NULL,                  -- ISO 8601, UTC
  editada_em    TEXT NOT NULL,
  excluida_em   TEXT                            -- NULL = ativa; preenchida = na lixeira
);

CREATE TABLE tags (
  id     INTEGER PRIMARY KEY,
  nome   TEXT NOT NULL UNIQUE,                  -- livre: minúsculo; versículo: forma canônica
  tipo   TEXT NOT NULL CHECK (tipo IN ('livre','versiculo')),
  -- preenchidos só para tipo = 'versiculo':
  livro        INTEGER,                         -- 1..66
  capitulo     INTEGER,
  verso_inicio INTEGER,                         -- NULL = capítulo inteiro
  verso_fim    INTEGER
);

CREATE TABLE nota_tags (
  nota_id INTEGER NOT NULL REFERENCES notas(id) ON DELETE CASCADE,
  tag_id  INTEGER NOT NULL REFERENCES tags(id)  ON DELETE CASCADE,
  origem  TEXT NOT NULL CHECK (origem IN ('manual','auto')),
  PRIMARY KEY (nota_id, tag_id)
);

CREATE VIRTUAL TABLE notas_fts USING fts5(
  titulo, conteudo,
  content='notas', content_rowid='id',
  tokenize='unicode61 remove_diacritics 2'
);
-- Triggers mantêm notas_fts sincronizada com notas (insert/update/delete).

CREATE INDEX idx_tags_versiculo ON tags(livro, capitulo) WHERE tipo = 'versiculo';
```

- **Modelos** ficam como arquivos Markdown em `notepi/modelos/` (`culto.md`, `guia_requisitos.md`), não no banco. Assim, adicionar um modelo é só criar um arquivo.
- A forma canônica da tag de versículo é `<Livro> <cap>:<v1>-<v2>` com o nome completo do livro (ex.: `Romanos 12:1-2`), para ficar igual não importa como foi escrita na nota.
- A versão do esquema fica em `PRAGMA user_version`, e as migrações são aplicadas na inicialização.

## 5. Reconhecimento de versículos

Entrada: o texto da nota. Saída: lista de referências normalizadas.

- Formatos aceitos: `Jo 3:16`, `Jo 3.16`, `João 3:16`, `1Co 13:4-7`, `1 Co 13:4-7`, `I Coríntios 13`, `Sl 23` (capítulo inteiro), `Rm 12:1,2` (vira 12:1-2 quando os versos são seguidos; senão, uma tag por verso).
- Abreviações: o padrão brasileiro mais comum (Gn, Êx/Ex, Lv, Nm, Dt… Mt, Mc, Lc, Jo, At, Rm, 1Co, 2Co, Gl, Ef, Fp, Cl… Ap), comparadas sem acento e sem diferença de maiúsculas.
- Validação: capítulo deve existir no livro (`livros.py` tem a quantidade de capítulos). Verso não é validado na v1, porque isso exigiria a tabela de versos por capítulo; só precisa ser maior ou igual a 1, e o início não pode passar do fim.
- Referência inválida (ex.: `Rm 99:1`) é ignorada e continua sendo texto comum.
- Ambiguidade Jó × João: a comparação de abreviações **leva o acento em conta só neste caso**. `Jó` (com acento) é o livro de Jó; `Jo` (sem acento) é sempre João. Os nomes completos `Jó` e `João` também funcionam.
- As tags automáticas são recalculadas toda vez que a nota é salva (`origem='auto'`); as tags manuais não são mexidas.

**Busca por versículo**: buscar "Romanos 12" encontra todas as tags com `livro=45 AND capitulo=12`, qualquer que seja o verso. Buscar "Romanos 12:2" encontra as tags cujo intervalo contém o verso 2 ou que valem para o capítulo inteiro.

## 6. Busca e notas relacionadas

- **Busca**: uma consulta FTS5 em `notas_fts`, ordenada por `bm25`, com trecho destacado por `snippet()`. Se o texto da busca for uma referência bíblica, os resultados por tag de versículo vêm primeiro. Filtros: área, modelo e tag. Notas na lixeira não aparecem.
- **Notas relacionadas** (na tela "Ver nota"): as outras notas ordenadas pela quantidade de tags em comum (no máximo 10, desempate pela edição mais recente). Para versículos, conta como tag em comum o mesmo livro e capítulo.

## 7. Telas

Desenhadas primeiro para o celular; no PC, o mesmo layout fica mais largo.

| Rota | Tela | Conteúdo |
|---|---|---|
| `GET /` | Início | Busca, botão **+ Nova nota**, notas recentes, filtro por área |
| `GET /notas/nova?modelo=` | Nova nota | Modelo, área, título, editor Markdown, tags; prévia dos versículos encontrados |
| `GET /notas/{id}` | Ver nota | Markdown formatado, tags clicáveis, notas relacionadas |
| `GET /notas/{id}/editar` | Editar | Igual à nova nota |
| `GET /busca?q=&area=&modelo=&tag=` | Busca | Resultados com trecho destacado e filtros |
| `GET /tags` | Tags | Todas as tags com contagem; versículos agrupados por livro |
| `GET /tags/{id}` | Página da tag | Notas com essa tag (para versículo: o capítulo inteiro) |
| `GET /lixeira` | Lixeira | Notas excluídas, com restaurar |
| `GET /saude` | Saúde | Banco OK, último backup, espaço livre no cartão |
| `GET /exportar` | Exportar | Arquivo `.zip` com um `.md` por nota (front matter: área, tags, datas) |

Ações (POST via HTMX): salvar nota, excluir, restaurar, adicionar ou remover tag, prévia de versículos (`POST /versiculos/previa`, chamado enquanto você digita, com intervalo de 500 ms).

### Modelos iniciais

`culto.md`:
```markdown
**Data:** {{hoje}}
**Pregador:**
**Texto-base:**

## Pontos
-

## Aplicação
```

`guia_requisitos.md`:
```markdown
**Item:**

| Critério | O que olhar | Por quê |
|---|---|---|
|  |  |  |

## Marcas boas e por quê
-

## Evitar
-
```

## 8. Erros e casos especiais

| Situação | Comportamento |
|---|---|
| Sem conexão / Pi fora do ar | O editor salva um rascunho no `localStorage` a cada alteração. Aparece o aviso "Sem conexão: rascunho salvo neste aparelho". O app tenta enviar a cada 15 s e quando o navegador volta a ficar online. O rascunho só é apagado depois que o servidor confirma. |
| Edição em dois aparelhos | O formulário envia o `editada_em` que carregou. Se o banco tiver um valor mais novo, o servidor responde 409 e mostra as duas versões lado a lado, para você escolher qual fica ou juntar à mão. |
| Referência bíblica inválida | Ignorada como tag e mantida como texto. |
| Erro inesperado | Página simples "Algo deu errado; seu texto foi mantido". O erro vai para o log do journald, que fica só na RAM (`Storage=volatile`). |
| Excluir nota | Vai para a lixeira (`excluida_em`). Uma limpeza diária apaga de vez as notas com mais de 30 dias na lixeira. |
| Título vazio | Usa a primeira linha do conteúdo; se ela também estiver vazia, usa "Nota de <data>". |

## 9. Backup e cuidados com o cartão SD

- **Backup diário às 03:00** (systemd timer): usa a API de backup online do SQLite para criar `notas-AAAA-MM-DD.db` num pendrive (`/mnt/backup`) e envia para a nuvem com `rclone`. Mantém 30 dias. Depois, roda `PRAGMA integrity_check` na cópia, e o resultado aparece em `/saude`.
- **Exportação em Markdown** a qualquer momento, pela tela `/exportar`.
- **Cuidados com o SD** (feitos pelo `instalar.sh`): logs do journald só na RAM (`Storage=volatile`, no lugar do log2ram, que exige repositório de terceiros), `noatime` no `/etc/fstab`, swap em zram (desliga o dphys-swapfile; se o sistema já tiver `rpi-swap`, mantém), SQLite em WAL com `synchronous=NORMAL`.
- **Manual (documentado no README)**: usar um cartão de alta durabilidade, salvar uma imagem do cartão depois da instalação, fonte oficial de 5V/2,5A, desligar com `sudo shutdown now`, nobreak recomendado.

## 10. Testes

Com pytest, rodando no PC (Windows) e no Pi.

- `test_versiculos.py`: tabela de casos (válidos, inválidos, abreviações, intervalos, listas com vírgula, Jó/João, livros numerados).
- `test_busca.py`: ignora acentos, ordem por relevância, filtros, busca por versículo (capítulo e verso).
- `test_relacionadas.py`: ordem pelas tags em comum, regra de livro + capítulo para versículos.
- `test_notas.py`: criar, editar, conflito (409), lixeira, restaurar, limpeza aos 30 dias.
- `test_web.py`: as rotas de ponta a ponta com o `TestClient` do FastAPI e um banco temporário.
- `test_backup.py`: o backup gera um arquivo válido que pode ser aberto, e a rotação mantém 30 dias.

## 11. Instalação no Pi

`deploy/instalar.sh` (idempotente, pode rodar de novo sem estragar nada):
1. `apt install` python3-venv, sqlite3, rclone, rsync e curl (e zram-tools, se o sistema não tiver `rpi-swap`); configura o journald só na RAM.
2. Cria o usuário de sistema `notepi`, `/opt/notepi` (código + venv) e `/var/lib/notepi` (banco).
3. Instala `notepi.service`, `notepi-backup.service` e `notepi-backup.timer`.
4. Aplica `noatime` e desliga o swap no cartão.
5. Instala o Tailscale e expõe o app com `tailscale serve --https=443 http://127.0.0.1:8000`.

O Uvicorn escuta só em `127.0.0.1:8000`, sem acesso direto pela rede local; quem expõe o app é o Tailscale.

## 12. Estrutura do repositório

```
NotePi/
├─ notepi/
│  ├─ __init__.py
│  ├─ app.py            # cria o FastAPI
│  ├─ config.py
│  ├─ texto.py
│  ├─ db.py
│  ├─ livros.py
│  ├─ versiculos.py
│  ├─ notas.py
│  ├─ tags.py
│  ├─ busca.py
│  ├─ backup.py
│  ├─ manutencao.py     # python -m notepi.manutencao (timer diário)
│  ├─ modelos/          # __init__.py, culto.md, guia_requisitos.md
│  └─ web/
│     ├─ rotas.py
│     ├─ templates/
│     └─ static/        # htmx.min.js, css, rascunho.js
├─ tests/
├─ deploy/
├─ docs/superpowers/specs/
├─ pyproject.toml
└─ README.md
```
