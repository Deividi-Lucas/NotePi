# NotePi — pendências para a v1.1

Itens apontados nas revisões da v1 (2026-11-11) que não bloqueiam o uso e ficaram para depois.
Nada aqui perde dados; são melhorias de robustez, testes e conforto.

## Vale fazer primeiro
- **Versículos:** "Gn 1. 5 minutos" vira a tag Gênesis 1:5. O separador `.` aceita espaço depois; exigir ponto colado (`Jo 3.16`).
- **Busca:** `except sqlite3.OperationalError` amplo demais esconde erro real como "0 resultados". Relançar quando não for erro do FTS5.
- **Tags/busca:** número de tag gigante (> 2^63) em `/busca?tag=` ou `/tags/{id}` dá 500. Limitar o tamanho.
- **Manutenção:** se `NOTEPI_DB` apontar para um caminho errado, um banco vazio é criado e copiado. Falhar se o arquivo não existir.
- **Manutenção:** com pendrive cheio, o backup falha antes da rotação e os backups param. Rotacionar antes ou no `finally`.
- **Edição:** nota movida para a lixeira entre a checagem e o UPDATE gera `ConflitoEdicao(None)` e 500.
- **Rascunho:** voltar para a página pelo cache do navegador (bfcache) pode deixar o botão Salvar desabilitado. Usar `pageshow` → `liberar()`.
- **Banco novo:** dois primeiros acessos simultâneos podem rodar a migração duas vezes. Migrar uma vez na inicialização.

## Instalação no Pi
- Atualizar com `tar -x` sobre `~/NotePi` deixa arquivos apagados no lugar. Extrair numa pasta nova.
- Cópia na nuvem nunca é limpa (o pendrive guarda 30 dias, a nuvem guarda tudo).
- `rclone authorize`: melhor usar o comando que o próprio `rclone config` imprime.
- `sed` no `/etc/fstab` sem cópia de segurança; `DNSName` vazio se o MagicDNS estiver desligado.
- Serviço sem endurecimento do systemd (`ProtectSystem=strict`, `NoNewPrivileges`).
- `notepi-manutencao.service` sem `After=time-sync.target` (o Pi 3B não tem relógio próprio).

## Interface
- Erros 404/422 de endereços desconhecidos aparecem em JSON e em inglês.
- Editar com área inválida troca para "Geral" sem avisar.
- "Tirar filtro" de tag na busca também apaga os filtros de área e modelo.
- Links do topo com área de toque pequena no celular.
- Título automático pode ficar com `**` no meio ("Data:** 10/11/2026").

## Testes
- O comportamento do `rascunho.js` só é checado por presença de texto; um teste de navegador (Playwright) cobriria de verdade.
- Sem teste para `config.carregar()`, `tags.nomes_manuais`/`obter`, filtro por modelo na busca e DELETE no índice FTS.
- Aviso `StarletteDeprecationWarning` (httpx) nos testes web.
