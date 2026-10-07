"""
Configurações do Monitor de Preços — TCL C6K (55"/65") e C6KS (50")
"""
import os
import json
from datetime import date

# ============================================================
# MODELOS MONITORADOS + PREÇO-ALVO
# ============================================================
# IMPORTANTE: os alvos são o TOTAL PARCELADO SEM JUROS no cartão, não o preço no Pix.
# No Pix as lojas costumam dar 5% a 15% de desconto, mas como a compra vai ser
# parcelada no cartão no máximo de vezes SEM JUROS, é esse total que importa.
# Parcelamento com juros não conta (o monitor ignora).
#
# Como os alvos foram definidos (pesquisa feita em 06/10/2026):
#   55" — hoje: ~R$ 3.400 sem juros (Amazon 12x, Magalu 10x).
#         Black Friday 2025: ~R$ 2.400–2.420 parcelado sem juros (Amazon com cupom, ML em 21x) — o menor já visto.
#         Ofertas boas em jul/2026: ~R$ 2.670–2.690.
#   65" — hoje: ~R$ 4.300 sem juros (Amazon 12x, Magalu 10x).
#         Black Friday 2025: ~R$ 3.050 em 12x sem juros (com cupom); ML ~R$ 3.460 parcelado.
#         Ofertas boas em jul/2026: ~R$ 3.220–3.400.
#   50" (C6KS) — já apareceu por R$ 1.800–2.200 com cupom; "normal" era ~R$ 2.300–2.500.
#         Parece ter saído de linha (sumiu da KaBuM e do Zoom) — pode nem aparecer.
#
# "excelente" = perto do menor preço da história → compre na hora (alerta urgente)
# "bom"       = preço bom de Black Friday → vale a pena comprar
MODELOS = {
    "50": {
        "nome": 'TCL QD-Mini LED C6KS 50"',
        "termo_busca": "TCL 50C6KS",
        "zoom_urls": ["https://www.zoom.com.br/tv/smart-tv-qd-mini-led-50-tcl-4k-c6ks"],
        "alvo_excelente": 2000,
        "alvo_bom": 2300,
    },
    "55": {
        "nome": 'TCL QD-Mini LED C6K 55"',
        "termo_busca": "TCL 55C6K",
        "zoom_urls": ["https://www.zoom.com.br/tv/smart-tv-mini-led-55-tcl-4k-55c6k"],
        "alvo_excelente": 2500,
        "alvo_bom": 2800,
    },
    "65": {
        "nome": 'TCL QD-Mini LED C6K 65"',
        "termo_busca": "TCL 65C6K",
        "zoom_urls": ["https://www.zoom.com.br/tv/smart-tv-qd-mini-led-65-tcl-4k-65c6k"],
        "alvo_excelente": 3200,
        "alvo_bom": 3500,
    },
}

# Tamanhos que mandam alerta pro celular (tire os que você não quer comprar)
TAMANHOS_ALERTA = ["50", "55", "65"]

# ============================================================
# REGRAS DE ALERTA
# ============================================================
# Ofertas com MENOS parcelas SEM JUROS que isso não geram alerta no celular.
# (Quando a loja não informa o parcelamento sem juros, o alerta é enviado com um aviso.)
PARCELAS_MINIMAS = 10

# Depois de avisar uma oferta, só avisa de novo se o preço cair pelo menos isso (R$)...
QUEDA_MINIMA_REALERTA = 50
# ...ou se a oferta sumir por mais que isso (horas) e depois voltar.
HORAS_PARA_ESQUECER_OFERTA = 6

# Resumo diário no celular (melhor preço de cada tamanho) — confirma que o monitor está vivo
RESUMO_DIARIO = True
RESUMO_DIARIO_HORA = 20  # envia na primeira verificação depois dessa hora

# Termos buscados no Pelando (comunidade de promoções — pega cupom e Mercado Livre)
PELANDO_TERMOS = ["c6k", "c6ks"]

# ============================================================
# INTERVALOS DE MONITORAMENTO (em minutos)
# ============================================================
INTERVALO_NORMAL = 60        # Fora da semana da Black Friday
INTERVALO_BLACK_FRIDAY = 15  # Durante a semana da Black Friday

# Black Friday 2026 = 27/11. A semana inteira (até a Cyber Monday) verifica mais rápido.
BLACK_FRIDAY_INICIO = date(2026, 11, 20)
BLACK_FRIDAY_FIM = date(2026, 12, 1)


def em_semana_black_friday(dia: date = None) -> bool:
    dia = dia or date.today()
    return BLACK_FRIDAY_INICIO <= dia <= BLACK_FRIDAY_FIM


def intervalo_atual() -> int:
    """Intervalo de verificação (minutos) para hoje."""
    return INTERVALO_BLACK_FRIDAY if em_semana_black_friday() else INTERVALO_NORMAL

# ============================================================
# CAMINHOS
# ============================================================
BASE_DIR = os.path.dirname(os.path.abspath(__file__))
HISTORICO_DIR = os.path.join(BASE_DIR, "historico")
# Histórico com preço NO CARTÃO. (O antigo precos.json guardava o preço do Pix e ficou de lado.)
HISTORICO_PATH = os.path.join(HISTORICO_DIR, "precos_cartao.json")
ESTADO_PATH = os.path.join(HISTORICO_DIR, "estado_alertas.json")
LOG_PATH = os.path.join(HISTORICO_DIR, "monitor.log")

# Garante que a pasta de histórico exista
os.makedirs(HISTORICO_DIR, exist_ok=True)

# ============================================================
# NOTIFICAÇÕES NO CELULAR (WhatsApp, ntfy, Telegram)
# ============================================================
# Configure com:  python monitor_precos.py --configurar-whatsapp
#                 python monitor_precos.py --configurar-ntfy
#                 python monitor_precos.py --configurar-telegram
# Na nuvem (GitHub Actions) as chaves vêm dos "Secrets" do repositório (variáveis de ambiente).
NOTIFICACOES_CONFIG_PATH = os.path.join(BASE_DIR, "notificacoes_config.json")


def carregar_notificacoes() -> dict:
    """Carrega a configuração dos canais de notificação (arquivo local + variáveis de ambiente)."""
    cfg = {}
    if os.path.exists(NOTIFICACOES_CONFIG_PATH):
        with open(NOTIFICACOES_CONFIG_PATH, "r", encoding="utf-8") as f:
            cfg = json.load(f)
    env = os.environ.get
    if env("TELEGRAM_TOKEN") and env("TELEGRAM_CHAT_ID"):
        cfg["telegram"] = {"token": env("TELEGRAM_TOKEN"), "chat_id": env("TELEGRAM_CHAT_ID")}
    if env("WHATSAPP_TELEFONE") and env("WHATSAPP_APIKEY"):
        cfg["whatsapp"] = {"telefone": env("WHATSAPP_TELEFONE"), "apikey": env("WHATSAPP_APIKEY")}
    if env("NTFY_TOPICO"):
        cfg["ntfy"] = {"topico": env("NTFY_TOPICO"), "servidor": "https://ntfy.sh"}
    return cfg


def salvar_notificacoes(cfg: dict):
    """Salva a configuração dos canais de notificação."""
    with open(NOTIFICACOES_CONFIG_PATH, "w", encoding="utf-8") as f:
        json.dump(cfg, f, ensure_ascii=False, indent=2)

# ============================================================
# NAVEGADOR
# ============================================================
HEADLESS = True  # True = navegador invisível, False = mostra o navegador
TIMEOUT = 20000  # Timeout de navegação em ms (20 segundos)

# Na nuvem a Amazon bloqueia (erro 503 para servidores), então lá o workflow desliga as
# fontes que precisam de navegador. O Zoom continua trazendo o preço da Amazon (sem parcelas).
USAR_NAVEGADOR = os.environ.get("MONITOR_SEM_NAVEGADOR") != "1"

USER_AGENTS = [
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/131.0.0.0 Safari/537.36",
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/130.0.0.0 Safari/537.36",
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64; rv:132.0) Gecko/20100101 Firefox/132.0",
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/131.0.0.0 Safari/537.36 Edg/131.0.0.0",
]
