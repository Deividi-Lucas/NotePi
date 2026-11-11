// Guarda o que você digita no próprio aparelho (localStorage) e só apaga
// depois que o servidor confirmar que salvou. Se a conexão cair, tenta de novo.
(function () {
  "use strict";
  var form = document.getElementById("form-nota");
  if (!form) return;

  var chave = "notepi:rascunho:" + form.dataset.chaveRascunho;
  var aviso = document.getElementById("aviso-rascunho");
  var CAMPOS = ["titulo", "conteudo", "area", "tags"];
  var INTERVALO_MS = 15000;
  var tentativa = null;

  function mostrar(msg) {
    aviso.textContent = msg || "";
    aviso.hidden = !msg;
  }
  function ler() {
    try { return JSON.parse(localStorage.getItem(chave)); } catch (e) { return null; }
  }
  function gravar() {
    var dados = {};
    CAMPOS.forEach(function (n) { if (form.elements[n]) dados[n] = form.elements[n].value; });
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
      CAMPOS.forEach(function (n) {
        if (form.elements[n] && salvo[n] !== undefined) form.elements[n].value = salvo[n];
      });
      mostrar("Rascunho restaurado deste aparelho.");
      form.elements.conteudo.dispatchEvent(new Event("input", { bubbles: true }));
    }
  }

  form.addEventListener("input", gravar);
  form.addEventListener("change", gravar);

  function agendar() {
    clearTimeout(tentativa);
    tentativa = setTimeout(enviar, INTERVALO_MS);
  }

  function enviar() {
    clearTimeout(tentativa);
    tentativa = null;
    fetch(form.action, { method: "POST", body: new FormData(form) })
      .then(function (resposta) {
        if (resposta.ok) {
          apagar();
          window.location.href = resposta.url;
          return;
        }
        if (resposta.status === 409) {
          return resposta.text().then(function (html) {
            document.open();
            document.write(html);
            document.close();
          });
        }
        mostrar("O servidor não conseguiu salvar (erro " + resposta.status +
                "). Seu texto continua guardado neste aparelho.");
      })
      .catch(function () {
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
