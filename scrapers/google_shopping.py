"""
Scraper para Google Shopping — Agrega preços de vários sites.
"""
import re
import logging
from scrapers.base import ScraperBase, Oferta

logger = logging.getLogger(__name__)


class GoogleShoppingScraper(ScraperBase):
    NOME_SITE = "Google Shopping"

    def _get_url(self, termo: str) -> str:
        from urllib.parse import quote_plus
        return f"https://www.google.com.br/search?q={quote_plus(termo)}&tbm=shop&hl=pt-BR"

    def buscar(self, tamanho: str, termo_busca: str) -> list[Oferta]:
        def _executar():
            ofertas = []
            page = self.nova_pagina()
            try:
                url = self._get_url(termo_busca)
                logger.info(f"[{self.NOME_SITE}] Buscando: {url}")
                page.goto(url, wait_until="domcontentloaded")
                page.wait_for_timeout(3000)

                # Aceitar cookies do Google
                try:
                    page.click("button#L2AGLb", timeout=2000)
                except Exception:
                    pass

                # Cards de resultado do Google Shopping
                seletores_cards = [
                    "div.sh-dgr__gr-auto",
                    "div.sh-dgr__content",
                    "div[class*='sh-dlr__list-result']",
                    "div.KZmu8e",
                    "div[data-docid]",
                ]

                cards = []
                for seletor in seletores_cards:
                    cards = page.query_selector_all(seletor)
                    if cards:
                        logger.info(f"[{self.NOME_SITE}] Seletor '{seletor}' encontrou {len(cards)} cards")
                        break

                for card in cards[:15]:
                    try:
                        nome = ""
                        for sel in ["h3", "h4", "a[class*='translate-content'] span", "[class*='title']"]:
                            el = card.query_selector(sel)
                            if el:
                                nome = el.inner_text().strip()
                                if nome:
                                    break

                        if not nome or not self.validar_produto(nome, tamanho):
                            continue

                        preco = None
                        texto_card = card.inner_text()
                        matches = re.findall(r'R\$\s*([\d.,]+)', texto_card)
                        for match in matches:
                            p = self.limpar_preco("R$ " + match)
                            if p:
                                if preco is None or p < preco:
                                    preco = p

                        if not preco:
                            continue

                        vendedor = ""
                        for sel in ["span[class*='merchant']", "span[class*='store']", "div[class*='aULzUe']"]:
                            el = card.query_selector(sel)
                            if el:
                                vendedor = el.inner_text().strip()
                                if vendedor:
                                    break

                        link_el = card.query_selector("a[href*='shopping']") or card.query_selector("a")
                        url_oferta = ""
                        if link_el:
                            url_oferta = link_el.get_attribute("href") or ""
                            if url_oferta.startswith("/"):
                                url_oferta = "https://www.google.com.br" + url_oferta

                        site_label = f"Google Shopping ({vendedor})" if vendedor else self.NOME_SITE
                        ofertas.append(Oferta(
                            site=site_label, nome_produto=nome[:150], preco=preco,
                            url=url_oferta, vendedor=vendedor, tamanho=tamanho,
                        ))
                    except Exception as e:
                        logger.debug(f"[{self.NOME_SITE}] Erro card: {e}")
                        continue

                # FALLBACK: extração por texto
                if not ofertas:
                    ofertas = self.extrair_ofertas_do_texto(page, tamanho, self.NOME_SITE)

            except Exception as e:
                logger.error(f"[{self.NOME_SITE}] Erro na busca: {e}")
            finally:
                page.close()
            return ofertas

        return self._tentar_com_retry(_executar)
