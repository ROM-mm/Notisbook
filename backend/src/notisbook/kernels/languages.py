"""Linguagens de célula e seus rótulos de exibição (fonte única; sem dependências)."""

from typing import Literal

CellLanguage = Literal["python", "sql", "duckdb"]

CELL_LANGUAGE_LABELS: dict[CellLanguage, str] = {"python": "Python", "sql": "Spark SQL", "duckdb": "DuckDB"}
