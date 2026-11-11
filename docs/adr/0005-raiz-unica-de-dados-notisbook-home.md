# ADR-0005: Raiz única de dados em NOTISBOOK_HOME

**Status:** Proposto
**Data:** 2026-11-11 (geração do registro; data da decisão não comprovada)
**Decisores:** Não identificados no material analisado

## Contexto
Ambientes, warehouse, catálogo e preferências precisam de um local previsível.

## Decisão
Todos os dados do Notisbook ficam em `~/.notisbook`, sobrescrevível só por `NOTISBOOK_HOME`, criada no start. Exceção observada: kernelspecs e connection files ficam nos diretórios padrão do Jupyter (`jupyter_data_dir()`, `jupyter_runtime_dir()`).

Motivação histórica não recuperada do código.

## Alternativas Consideradas
Não identificadas no material analisado.

## Consequências

### Positivas
- Um único local para backup ou limpeza.
- Proteções de exclusão sabem qual pasta não pode ser apagada.

### Negativas
- Kernelspecs ficam fora da raiz e sobrevivem à remoção de `~/.notisbook`.

### Riscos
- Kernelspecs órfãos após apagar a raiz manualmente. Mitigação: remoção de ambiente pela interface.

## Validação
- **Evidência no código:** `backend/src/notisbook/config.py:20-33`, `backend/src/notisbook/spark/kernelspec.py:51-60`
- **Como confirmar:** `grep -n NOTISBOOK_HOME backend/src/notisbook/config.py`

---

**Autor:** Romerito Morais

**Versão:** 20261111125851

**Data:** 2026-11-11 12:58:51

**SKILL:** Document
