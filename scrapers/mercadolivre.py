"""
Scraper para Mercado Livre.
"""
import re
import logging
from scrapers.base import ScraperBase, Oferta

logger = logging.getLogger(__name__)


class MercadoLivreScraper(ScraperBase):
    NOME_SITE = "Mercado Livre"

    def _get_url(self, termo: str) -> str:
        from urllib.parse import quote_plus
        return f"https://lista.mercadolivre.com.br/{quote_plus(termo)}"

    def buscar(self, tamanho: str, termo_busca: str) -> list[Oferta]:
        def _executar():
            ofertas = []
            page = self.nova_pagina()
            try:
                url = self._get_url(termo_busca)
                logger.info(f"[{self.NOME_SITE}] Buscando: {url}")
                page.goto(url, wait_until="domcontentloaded")
                page.wait_for_timeout(4000)

                # Tenta fechar popup
                for btn_sel in [
                    "button[data-testid='action:understood-button']",
                    "button.cookie-consent-banner-opt-out__action--primary",
                ]:
                    try:
                        page.click(btn_sel, timeout=1500)
                    except Exception:
                        pass

                # Seletores para cards de produto
                seletores_cards = [
                    "div.poly-card",
                    "li.ui-search-layout__item",
                    "div.ui-search-result",
                    "li[class*='search-layout']",
                    "div[class*='poly-card']",
                    "a[href*='/MLB-']",
                ]

                cards = []
                for seletor in seletores_cards:
                    cards = page.query_selector_all(seletor)
                    if cards:
                        logger.info(f"[{self.NOME_SITE}] Seletor '{seletor}' encontrou {len(cards)} cards")
                        break

                for card in cards[:15]:
                    try:
                        # Nome do produto
                        nome = ""
                        for sel in ["h2", "a.poly-component__title", "[class*='title'] a", "[class*='title']", "a[title]"]:
                            el = card.query_selector(sel)
                            if el:
                                nome = el.inner_text().strip() or el.get_attribute("title") or ""
                                if nome:
                                    break
                        if not nome:
                            texto_bruto = card.inner_text()
                            for linha in texto_bruto.split("\n"):
                                linha = linha.strip()
                                if len(linha) > 15 and "C6K" in linha.upper():
                                    nome = linha
                                    break

                        if not nome or not self.validar_produto(nome, tamanho):
                            continue

                        # Preço
                        preco = None
                        preco_el = card.query_selector("span.andes-money-amount__fraction")
                        if preco_el:
                            preco_texto = preco_el.inner_text().strip()
                            centavos_el = card.query_selector("span.andes-money-amount__cents")
                            if centavos_el:
                                preco_texto += "," + centavos_el.inner_text().strip()
                            preco = self.limpar_preco(preco_texto)

                        if not preco:
                            texto = card.inner_text()
                            matches = re.findall(r'(\d{1,3}(?:\.\d{3})+(?:,\d{2})?)', texto)
                            for m in matches:
                                p = self.limpar_preco(m)
                                if p:
                                    preco = p
                                    break

                        if not preco:
                            continue

                        link_el = card.query_selector("a[href*='mercadolivre']") or card.query_selector("a[href*='MLB']") or card.query_selector("a")
                        url_oferta = ""
                        if link_el:
                            url_oferta = link_el.get_attribute("href") or ""
                        elif card.evaluate("el => el.tagName") == "A":
                            url_oferta = card.get_attribute("href") or ""

                        ofertas.append(Oferta(
                            site=self.NOME_SITE, nome_produto=nome[:150], preco=preco,
                            url=url_oferta, tamanho=tamanho,
                        ))
                    except Exception as e:
                        logger.debug(f"[{self.NOME_SITE}] Erro card: {e}")
                        continue

                # FALLBACK: extração por texto se não achou nada com CSS
                if not ofertas:
                    ofertas = self.extrair_ofertas_do_texto(page, tamanho)

            except Exception as e:
                logger.error(f"[{self.NOME_SITE}] Erro na busca: {e}")
            finally:
                page.close()
            return ofertas

        return self._tentar_com_retry(_executar)
