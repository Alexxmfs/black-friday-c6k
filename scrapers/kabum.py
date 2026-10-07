"""
Scraper para KaBuM!

Não precisa de navegador: a página de busca traz os produtos num JSON (__NEXT_DATA__),
com preço no cartão, preço no Pix, parcelamento e promoções relâmpago ativas.
"""
import json
import time
import logging
from scrapers.base import ScraperBase, Oferta, baixar_html, extrair_next_data, extrair_parcelamento, soma_bate

logger = logging.getLogger(__name__)


class KabumScraper(ScraperBase):
    NOME_SITE = "KaBuM!"
    USA_NAVEGADOR = False

    def _get_url(self, termo: str) -> str:
        # A KaBuM usa hífen no lugar de espaço: "TCL 55C6K" -> /busca/tcl-55c6k
        return f"https://www.kabum.com.br/busca/{termo.strip().lower().replace(' ', '-')}"

    def buscar(self, tamanho: str, termo_busca: str) -> list[Oferta]:
        return self._tentar_com_retry(lambda: self._buscar(tamanho, termo_busca))

    def _buscar(self, tamanho: str, termo_busca: str) -> list[Oferta]:
        url = self._get_url(termo_busca)
        logger.info(f"[{self.NOME_SITE}] Buscando: {url}")
        dados = extrair_next_data(baixar_html(url))["props"]["pageProps"]["data"]
        if isinstance(dados, str):
            dados = json.loads(dados)

        agora = time.time()
        ofertas = []
        for p in dados["catalogServer"]["data"]:
            nome = p.get("name") or ""
            if not p.get("available") or not self.validar_produto(nome, tamanho):
                continue

            # "price" = no cartão; "priceWithDiscount" = no Pix
            preco = p.get("price")
            preco_pix = p.get("priceWithDiscount")
            # Promoção relâmpago ativa (ex: "ESQUENTA 10DO10") substitui o preço normal
            promo = p.get("offer") or {}
            if promo and promo.get("startsAt", 0) <= agora <= promo.get("endsAt", 0):
                preco = promo.get("price") or preco
                preco_pix = promo.get("priceWithDiscount") or preco_pix

            if not preco or preco < 1500:  # descarta acessórios
                continue

            # "maxInstallment" vem sem rótulo ("10x de R$ 369,90"): só é sem juros
            # se as parcelas somarem exatamente o preço no cartão
            parcelas, valor_parcela = extrair_parcelamento(p.get("maxInstallment", ""))
            if parcelas and not soma_bate(parcelas, valor_parcela, preco):
                parcelas = valor_parcela = None
            ofertas.append(Oferta(
                site=self.NOME_SITE,
                nome_produto=nome[:150],
                preco=float(preco),
                preco_pix=float(preco_pix) if preco_pix else None,
                parcelas=parcelas,
                valor_parcela=valor_parcela,
                url=f"https://www.kabum.com.br/produto/{p['code']}/{p.get('friendlyName', '')}",
                vendedor=p.get("sellerName") or "",
                tamanho=tamanho,
            ))
        return ofertas
