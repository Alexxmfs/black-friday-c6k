"""
Scraper para o Zoom (zoom.com.br) — comparador que lista ofertas de várias lojas
(Magazine Luiza, Fast Shop, KaBuM!, Amazon, Webcontinental...) já com o preço no Pix
E o parcelamento sem juros. Cobre a Magalu, que bloqueia acesso automatizado direto.

Não precisa de navegador: os dados vêm num JSON (__NEXT_DATA__) dentro da página.
"""
import logging
from config import MODELOS
from scrapers.base import ScraperBase, Oferta, baixar_html, extrair_next_data, soma_bate

logger = logging.getLogger(__name__)


class ZoomScraper(ScraperBase):
    NOME_SITE = "Zoom"
    USA_NAVEGADOR = False

    def buscar(self, tamanho: str, termo_busca: str) -> list[Oferta]:
        ofertas = []
        for url in MODELOS[tamanho].get("zoom_urls", []):
            ofertas.extend(self._tentar_com_retry(lambda: self._ofertas_da_pagina(url, tamanho)))
        return ofertas

    def _ofertas_da_pagina(self, url: str, tamanho: str) -> list[Oferta]:
        logger.info(f"[{self.NOME_SITE}] Buscando: {url}")
        estado = extrair_next_data(baixar_html(url))["props"]["initialReduxState"]

        ofertas = []
        for o in estado["offers"].get("offerList", []):
            preco_pix = o.get("price") or None
            parcelas = o.get("numParcels") or None
            valor_parcela = o.get("parcelValue") or None
            # Total parcelado; sem parcelamento informado, fica o preço anunciado
            preco = o.get("totalParceledValue") or o.get("totalPrice") or preco_pix
            if not preco:
                continue
            # O Zoom não escreve "sem juros", mas o parcelamento dele é o sem juros da loja
            # (conferido na Magalu: "R$ 3.400,00 em 10x de R$ 340,00 sem juros"). Por segurança,
            # se as parcelas não somam o total, ou se o total passa muito do Pix (desconto de
            # Pix vai até ~15%), deve ter juros embutidos: fica como "não informado".
            if parcelas and (
                not valor_parcela
                or not soma_bate(parcelas, valor_parcela, preco)
                or (preco_pix and preco > preco_pix * 1.18)
            ):
                parcelas = valor_parcela = None
            loja = o.get("sellerName") or "?"
            ofertas.append(Oferta(
                site=loja,
                via=self.NOME_SITE,
                nome_produto=(o.get("name") or "")[:150],
                preco=float(preco),
                preco_pix=float(preco_pix) if preco_pix else None,
                parcelas=parcelas,
                valor_parcela=valor_parcela,
                url=url,  # página do Zoom com o botão "Ir à loja" de cada oferta
                vendedor=loja,
                tamanho=tamanho,
            ))
        return ofertas
