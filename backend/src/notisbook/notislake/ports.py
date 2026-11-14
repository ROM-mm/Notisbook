"""Escolha de portas TCP livres em loopback para o MinIO local.

A checagem é inerentemente racy (a porta pode ser tomada entre a escolha e o uso);
quem sobe o processo deve tentar de novo em caso de conflito.
"""

from __future__ import annotations

import socket
from contextlib import ExitStack

LOOPBACK = "127.0.0.1"
_MIN_PORT = 1024  # exclusivo


def is_free(port: int) -> bool:
    """True se `port` (faixa 1025–65535) pode ser ligada em 127.0.0.1 agora."""
    if not _MIN_PORT < port < 65536:
        return False
    with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as sock:
        try:
            sock.bind((LOOPBACK, port))
        except OSError:
            return False
    return True


def pick_free_ports(n: int) -> list[int]:
    """Devolve `n` portas distintas, livres em 127.0.0.1 e acima de 1024.

    Os sockets ficam abertos até todas serem escolhidas, o que garante portas distintas.
    """
    if n < 1:
        raise ValueError("n must be at least 1")
    ports: list[int] = []
    with ExitStack() as stack:
        while len(ports) < n:
            sock = stack.enter_context(socket.socket(socket.AF_INET, socket.SOCK_STREAM))
            sock.bind((LOOPBACK, 0))
            port = sock.getsockname()[1]
            if port > _MIN_PORT and port not in ports:
                ports.append(port)
    return ports
