// Pede confirmação antes de enviar formulários com data-confirmar="mensagem".
document.addEventListener("submit", function (evento) {
  var mensagem = evento.target.getAttribute && evento.target.getAttribute("data-confirmar");
  if (mensagem && !window.confirm(mensagem)) {
    evento.preventDefault();
  }
});
