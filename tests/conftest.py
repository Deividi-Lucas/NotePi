import pytest

from notepi.db import conectar


@pytest.fixture
def con():
    conexao = conectar(":memory:")
    yield conexao
    conexao.close()
