"""
Pelando (pelando.com.br) — comunidade onde as promoções boas aparecem em minutos,
de QUALQUER loja: Mercado Livre, Casas Bahia, AliExpress, ofertas com cupom...
(lojas que bloqueiam acesso automatizado, mas que a comunidade posta).

Não precisa de navegador: os posts vêm serializados na própria página (Astro).
"""
import re
import json
import html
import logging
from scrapers.base import baixar_html

logger = logging.getLogger(__name__)


def _desserializar_astro(valor):
    """O Astro serializa props como [tipo, valor]: 0 = valor/objeto, 1 = lista."""
    if not (isinstance(valor, list) and len(valor) == 2 and isinstance(valor[0], int)):
        return valor
    tipo, conteudo = valor
    if tipo == 0 and isinstance(conteudo, dict):
        return {k: _desserializar_astro(v) for k, v in conteudo.items()}
    if tipo == 1:
        return [_desserializar_astro(v) for v in conteudo]
    return conteudo


def buscar_pelando(termos: list[str]) -> list[dict]:
    """Retorna os posts mais recentes que batem com os termos (sem repetir)."""
    posts = {}
    for termo in termos:
        url = f"https://www.pelando.com.br/busca/{termo}"
        logger.info(f"[Pelando] Buscando: {url}")
        pagina = baixar_html(url)
        ilha = re.search(r'<astro-island[^>]*component-export="SearchFeedContent"[^>]*>', pagina)
        props = re.search(r'props="([^"]*)"', ilha.group(0)) if ilha else None
        if not props:
            raise ValueError("lista de ofertas não encontrada na página (layout mudou?)")

        dados = {k: _desserializar_astro(v) for k, v in json.loads(html.unescape(props.group(1))).items()}
        for d in dados["initialData"]["deals"]["deals"]:
            posts[d["id"]] = {
                "id": d["id"],
                "titulo": d.get("title") or "",
                "preco": d.get("price"),
                "status": d.get("status"),          # "active" ou "expired"
                "tipo": d.get("kind"),              # "promotion", "coupon", "discussion"
                "temperatura": d.get("temperature"),
                "criado_em": d.get("createdAt"),    # ISO, UTC
                "loja": (d.get("store") or {}).get("name", ""),
                "url": f"https://www.pelando.com.br/d/{d['slug']}",
            }
    return list(posts.values())
