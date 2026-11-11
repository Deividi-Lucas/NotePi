// Guarda o que você digita no próprio aparelho (localStorage) e só apaga
// depois que o servidor confirmar que salvou. Se a conexão cair, tenta de novo.
(function () {
  "use strict";
  var form = document.getElementById("form-nota");
  if (!form) return;

  var chave = "notepi:rascunho:" + form.dataset.chaveRascunho;
  var aviso = document.getElementById("aviso-rascunho");
  var CAMPOS = ["titulo", "conteudo", "area", "tags"];
  var CAMPOS_RASCUNHO = CAMPOS.concat(["editada_em_base"]);
  var INTERVALO_MS = 15000;
  var tentativa = null;
  var enviando = false;
  var botao = form.querySelector('button[type="submit"]');

  function mostrar(msg, comDescartar) {
    aviso.textContent = msg || "";
    aviso.hidden = !msg;
    if (msg && comDescartar) {
      var descartar = document.createElement("button");
      descartar.type = "button";
      descartar.className = "botao";
      descartar.textContent = "Descartar rascunho";
      descartar.addEventListener("click", function () {
        apagar();
        location.reload();
      });
      aviso.appendChild(document.createTextNode(" "));
      aviso.appendChild(descartar);
    }
  }
  function ler() {
    try { return JSON.parse(localStorage.getItem(chave)); } catch (e) { return null; }
  }
  function gravar() {
    var dados = {};
    CAMPOS_RASCUNHO.forEach(function (n) { if (form.elements[n]) dados[n] = form.elements[n].value; });
    try { localStorage.setItem(chave, JSON.stringify(dados)); } catch (e) { /* sem espaço: segue */ }
  }
  function apagar() {
    try { localStorage.removeItem(chave); } catch (e) { /* ignora */ }
  }

  // Ao abrir: se existe rascunho diferente do que veio do servidor, restaura.
  var salvo = ler();
  if (salvo) {
    var diferente = CAMPOS.some(function (n) {
      return form.elements[n] && salvo[n] !== undefined && salvo[n] !== form.elements[n].value;
    });
    if (diferente) {
      CAMPOS_RASCUNHO.forEach(function (n) {
        if (form.elements[n] && salvo[n] !== undefined) form.elements[n].value = salvo[n];
      });
      mostrar("Rascunho restaurado deste aparelho.", true);
      form.elements.conteudo.dispatchEvent(new Event("input", { bubbles: true }));
    }
  }

  form.addEventListener("input", gravar);
  form.addEventListener("change", gravar);

  function agendar() {
    clearTimeout(tentativa);
    tentativa = setTimeout(enviar, INTERVALO_MS);
  }

  function liberar() {
    enviando = false;
    botao.disabled = false;
  }

  function enviar() {
    if (enviando) return;
    enviando = true;
    botao.disabled = true;
    clearTimeout(tentativa);
    tentativa = null;
    fetch(form.action, { method: "POST", body: new FormData(form) })
      .then(function (resposta) {
        if (resposta.ok || resposta.redirected) {
          apagar();
          window.location.href = resposta.url;
          return;
        }
        if (resposta.status === 409) {
          return resposta.text().then(function (html) {
            document.open();
            document.write(html);
            document.close();
            liberar();
          });
        }
        if (resposta.status >= 500) {
          liberar();
          mostrar("Servidor fora do ar (erro " + resposta.status +
                  "): rascunho salvo neste aparelho. Vou tentar enviar de novo.");
          agendar();
          return;
        }
        liberar();
        mostrar("O servidor não conseguiu salvar (erro " + resposta.status +
                "). Seu texto continua guardado neste aparelho.");
      })
      .catch(function () {
        liberar();
        mostrar("Sem conexão: rascunho salvo neste aparelho. Vou tentar enviar de novo.");
        agendar();
      });
  }

  form.addEventListener("submit", function (ev) {
    ev.preventDefault();
    gravar();
    mostrar("Salvando…");
    enviar();
  });

  window.addEventListener("online", function () {
    if (tentativa) enviar();
  });
})();
