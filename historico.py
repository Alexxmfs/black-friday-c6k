"""
Gerenciamento do histórico de preços.
Salva e carrega dados em JSON com timestamps.
"""
import json
import os
from datetime import datetime
from typing import Optional
from config import HISTORICO_PATH, HISTORICO_DIR, PARCELAS_MINIMAS


def carregar_historico() -> dict:
    """
    Carrega o histórico de preços do arquivo JSON.

    Estrutura (preço = TOTAL NO CARTÃO):
    {
        "55": {
            "menor_preco": 3399.96,
            "menor_preco_site": "Amazon",
            "menor_preco_data": "2026-10-06T10:30:00",
            "registros": [
                {
                    "timestamp": "2026-10-06T10:30:00",
                    "site": "Amazon",
                    "via": "",
                    "preco": 3399.96,
                    "preco_pix": 3060.0,
                    "parcelas": 12,
                    "valor_parcela": 283.33,
                    "url": "https://...",
                    "nome_produto": "...",
                    ...
                },
                ...
            ]
        },
        ...
    }
    """
    if os.path.exists(HISTORICO_PATH):
        try:
            with open(HISTORICO_PATH, "r", encoding="utf-8") as f:
                return json.load(f)
        except (json.JSONDecodeError, IOError):
            return {}
    return {}


def salvar_historico(historico: dict):
    """Salva o histórico no arquivo JSON."""
    os.makedirs(HISTORICO_DIR, exist_ok=True)
    with open(HISTORICO_PATH, "w", encoding="utf-8") as f:
        json.dump(historico, f, ensure_ascii=False, indent=2)


def registrar_ofertas(ofertas: list, tamanho: str) -> dict:
    """
    Registra novas ofertas no histórico e diz se apareceu um novo menor preço.

    Returns:
        dict com:
            - novo_minimo: bool — se o menor total sem juros já registrado caiu
            - preco_anterior: float — menor preço anterior (None se é o 1º registro)
            - melhor: Oferta — oferta mais barata desta rodada
    """
    historico = carregar_historico()

    if tamanho not in historico:
        historico[tamanho] = {
            "menor_preco": None,
            "menor_preco_site": "",
            "menor_preco_data": "",
            "registros": [],
        }

    info_tamanho = historico[tamanho]
    resultado = {
        "novo_minimo": False,
        "preco_anterior": info_tamanho.get("menor_preco"),
        "melhor": None,
    }

    if not ofertas:
        return resultado

    # Registra cada oferta
    timestamp = datetime.now().isoformat()
    for oferta in ofertas:
        registro = oferta.to_dict()
        registro["timestamp"] = timestamp
        info_tamanho["registros"].append(registro)

    # Limita histórico a 5000 registros por tamanho
    if len(info_tamanho["registros"]) > 5000:
        info_tamanho["registros"] = info_tamanho["registros"][-5000:]

    # O menor preço histórico só considera ofertas com parcelamento informado e
    # com pelo menos PARCELAS_MINIMAS (sem parcelamento, o preço pode ser o do Pix)
    confiaveis = [o for o in ofertas if o.parcelamento_conhecido and o.parcelas >= PARCELAS_MINIMAS]
    if not confiaveis:
        salvar_historico(historico)
        return resultado
    melhor = min(confiaveis, key=lambda o: o.preco)
    resultado["melhor"] = melhor

    # Verifica se é novo mínimo
    menor_anterior = info_tamanho.get("menor_preco")
    if menor_anterior is None or melhor.preco < menor_anterior:
        resultado["novo_minimo"] = True
        info_tamanho["menor_preco"] = melhor.preco
        info_tamanho["menor_preco_site"] = melhor.loja
        info_tamanho["menor_preco_data"] = timestamp

    salvar_historico(historico)
    return resultado


def obter_menor_historico(tamanho: str) -> Optional[dict]:
    """Retorna informações sobre o menor preço histórico para um tamanho."""
    historico = carregar_historico()
    if tamanho in historico:
        info = historico[tamanho]
        if info.get("menor_preco") is not None:
            return {
                "preco": info["menor_preco"],
                "site": info["menor_preco_site"],
                "data": info["menor_preco_data"],
            }
    return None


def obter_ultimos_registros(tamanho: str, limite: int = 20) -> list:
    """Retorna os últimos N registros para um tamanho."""
    historico = carregar_historico()
    if tamanho in historico:
        return historico[tamanho].get("registros", [])[-limite:]
    return []


def exportar_csv(caminho: str):
    """Exporta todo o histórico para CSV."""
    import csv
    historico = carregar_historico()
    with open(caminho, "w", encoding="utf-8", newline="") as f:
        writer = csv.writer(f)
        writer.writerow(["Tamanho", "Data/Hora", "Site", "Total sem juros", "Parcelas sem juros",
                         "Valor da parcela", "Preço no Pix", "URL", "Produto"])
        for tamanho, info in historico.items():
            for reg in info.get("registros", []):
                site = reg.get("site", "")
                if reg.get("via"):
                    site += f" (via {reg['via']})"
                writer.writerow([
                    tamanho + '"',
                    reg.get("timestamp", ""),
                    site,
                    f'R$ {reg.get("preco", 0):.2f}',
                    reg.get("parcelas") or "",
                    f'R$ {reg["valor_parcela"]:.2f}' if reg.get("valor_parcela") else "",
                    f'R$ {reg["preco_pix"]:.2f}' if reg.get("preco_pix") else "",
                    reg.get("url", ""),
                    reg.get("nome_produto", ""),
                ])
