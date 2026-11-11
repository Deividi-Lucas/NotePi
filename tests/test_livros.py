from notepi import livros


def test_sao_66_livros_em_ordem():
    assert len(livros.LIVROS) == 66
    assert [l.numero for l in livros.LIVROS] == list(range(1, 67))
    assert livros.por_numero(45).nome == "Romanos"
    assert livros.por_numero(19).capitulos == 150


def test_busca_por_nome_e_abreviacao():
    assert livros.buscar_livro("", "Rm").numero == 45
    assert livros.buscar_livro("", "romanos").numero == 45
    assert livros.buscar_livro("", "Êx").numero == 2
    assert livros.buscar_livro("", "Ex").numero == 2
    assert livros.buscar_livro("1", "Co").numero == 46
    assert livros.buscar_livro("1", "Coríntios").numero == 46
    assert livros.buscar_livro("3", "Jo").numero == 64


def test_jo_e_joao():
    assert livros.buscar_livro("", "Jó").numero == 18
    assert livros.buscar_livro("", "JÓ").numero == 18
    assert livros.buscar_livro("", "Jo").numero == 43
    assert livros.buscar_livro("", "João").numero == 43


def test_desconhecido():
    assert livros.buscar_livro("", "Isaque") is None
    assert livros.buscar_livro("4", "Reis") is None
    assert livros.buscar_livro("", "de") is None
