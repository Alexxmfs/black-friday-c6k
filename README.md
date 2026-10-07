# 📺 Monitor de Preços — TCL C6K (55"/65") e C6KS (50")

Monitora o preço da **Smart TV TCL QD-Mini LED C6K/C6KS** nas lojas brasileiras e
**avisa no celular (WhatsApp)** quando aparecer um preço bom — pensado para a
**Black Friday 2026 (27/11)**.

> 💳 **O preço que vale é o TOTAL PARCELADO SEM JUROS, não o do Pix.**
> No Pix as lojas dão 5–15% de desconto, mas como a compra vai ser parcelada no cartão
> no máximo de vezes **sem juros**, o monitor compara e avisa sempre por esse total.
> Parcelamento com juros é ignorado.
> Ex. (06/10/2026): TV 55" na Amazon = R$ 3.060 no Pix, mas **R$ 3.399,96 em 12x sem juros** no cartão.
>
> Como o "sem juros" é conferido: a Amazon escreve "sem juros" (o que vier "com juros" é descartado);
> na KaBuM, as parcelas têm que somar exatamente o preço no cartão; no Zoom, o parcelamento é o
> sem juros da loja (conferido na Magalu) e é descartado se o total passar muito do preço no Pix.

## 🎯 Preços-alvo (total sem juros, em 10x ou mais)

| TV | Hoje (06/10) | ✅ Bom | 🔥 Excelente | Referência |
|----|-------------|--------|-------------|------------|
| 55" C6K | ~R$ 3.400 | **até R$ 2.800** | **até R$ 2.500** | Black Friday 2025: ~R$ 2.400 parcelado (menor da história); julho/2026: ~R$ 2.670 |
| 65" C6K | ~R$ 4.300 | **até R$ 3.500** | **até R$ 3.200** | Black Friday 2025: ~R$ 3.050 em 12x; julho/2026: ~R$ 3.220–3.400 |
| 50" C6KS | sem oferta | até R$ 2.300 | até R$ 2.000 | Parece ter saído de linha (sumiu da KaBuM, Amazon e Zoom) |

- **Bom** = preço de Black Friday, vale comprar.
- **Excelente** = perto do menor preço da história → compre na hora (alerta urgente).

Os alvos ficam em `config.py` (`alvo_bom` / `alvo_excelente`) — ajuste quando quiser.

## 🛒 De onde vêm os preços

| Fonte | O que cobre | Como |
|-------|-------------|------|
| **Zoom** | Magazine Luiza, Fast Shop, Webcontinental e outras | Lê o JSON da página (sem navegador) |
| **KaBuM!** | KaBuM! e parceiros (inclui promoções relâmpago) | Lê o JSON da página (sem navegador) |
| **Amazon** | Amazon | Navegador Chromium invisível (Playwright) |
| **Pelando** | Promoções postadas pela comunidade — inclusive **Mercado Livre, Casas Bahia, AliExpress e cupons** | Lê os posts da busca |

Desativados (out/2026): Mercado Livre exige login, Magalu e Casas Bahia bloqueiam acesso
automatizado, Google Shopping/Buscapé mudaram o layout. Os arquivos continuam em `scrapers/`.

## 🚀 Instalação

```bash
pip install -r requirements.txt
playwright install chromium
```

## 📱 Receber alertas no celular

Configure **pelo menos um** canal (pode usar mais de um ao mesmo tempo).
Depois de configurar, o programa mostra os valores para cadastrar no GitHub (se for usar a nuvem).

### Telegram (recomendado — oficial e instantâneo)
1. No Telegram, procure **@BotFather**, mande `/newbot` e siga as instruções. Ele te dá um **TOKEN**.
2. Abra a conversa com o seu bot novo e mande qualquer mensagem (ex: "oi").
3. Rode e cole o TOKEN:

```bash
python monitor_precos.py --configurar-telegram
```

### WhatsApp (CallMeBot — grátis)
1. Salve nos contatos do celular o número **+34 623 75 84 18** (ex: "CallMeBot")
2. Mande para ele pelo WhatsApp: `I allow callmebot to send me messages`
3. Em até 2 minutos ele responde com sua **APIKEY**
4. Rode e siga as instruções:

```bash
python monitor_precos.py --configurar-whatsapp
```

### Notificação push (app ntfy — grátis, sem cadastro)
Instale o app **ntfy** (Play Store / App Store) e rode:

```bash
python monitor_precos.py --configurar-ntfy
```

O programa gera um tópico secreto para você assinar no app. Tocar na notificação abre a oferta.

Para testar todos os canais configurados: `python monitor_precos.py --testar-notificacoes`

> 🔒 As chaves ficam em `notificacoes_config.json` — não compartilhe esse arquivo
> (ele não vai para o GitHub: está no `.gitignore`).

## ☁️ Rodar na nuvem, de graça — PC pode ficar desligado (recomendado)

O GitHub Actions roda o monitor nos servidores do GitHub, de graça, até 01/12:
de hora em hora, e **a cada 15 min na semana da Black Friday (20/11 a 01/12)**.
O histórico de preços fica salvo no próprio repositório.

1. Entre no [github.com](https://github.com) (crie a conta se não tiver) e clique em
   **New repository**: nome `monitor-tv-tcl`, **Public**, sem README → **Create repository**.
   (Público = minutos ilimitados de graça. Suas chaves NÃO ficam visíveis: vão nos Secrets.)
2. Envie o projeto para lá (na pasta do projeto; o GitHub abre uma janela pedindo login):

```bash
git remote add origin https://github.com/SEU_USUARIO/monitor-tv-tcl.git
```

```bash
git push -u origin main
```

3. No repositório: **Settings → Secrets and variables → Actions → New repository secret**.
   Cadastre os valores que o `--configurar-...` mostrou (ou rode `python monitor_precos.py --segredos-github`):
   - Telegram: `TELEGRAM_TOKEN` e `TELEGRAM_CHAT_ID`
   - WhatsApp: `WHATSAPP_TELEFONE` (ex: `+5511999998888`) e `WHATSAPP_APIKEY`
   - ntfy: `NTFY_TOPICO`
4. Aba **Actions** → **Monitor TV TCL C6K** → **Run workflow**. Deve chegar uma mensagem de
   teste no celular e aparecer um ✅ verde. Pronto — a partir daí roda sozinho.

Na nuvem a Amazon bloqueia o acesso direto (erro 503 para servidores); o preço dela continua
vindo pelo Zoom, só que sem o parcelamento. Zoom, KaBuM e Pelando funcionam normalmente.

> Depois da Black Friday: aba **Actions → Monitor TV TCL C6K → ⋯ → Disable workflow**
> (ou apague o repositório).

## ⏰ Ou: rodar neste PC (alternativa à nuvem)

Use **um ou outro** — com os dois ligados, os alertas chegam em dobro.
Depois de configurar o canal, o programa pergunta se quer ativar a verificação automática.
Ou ative a qualquer momento:

```bash
python monitor_precos.py --ativar-agendamento
```

Isso cria a tarefa **"Monitor TV TCL C6K"** no Agendador de Tarefas do Windows:
- roda escondida (sem abrir janela) até **02/12/2026**;
- verifica **de 60 em 60 min**, e **de 15 em 15 min de 20/11 a 01/12** (semana da Black Friday);
- o que acontece fica em `historico/monitor.log`.

Para desligar: `python monitor_precos.py --desativar-agendamento`

> ⚠️ Só funciona com o PC **ligado e com você logado** — dormindo/hibernando ele não verifica.
> Na semana da Black Friday, vale deixar o PC sem suspender (ao menos na tomada).

## 🔔 Quando chega alerta no celular

1. **Preço dentro do alvo** — o menor total parcelado sem juros (em 10x ou mais) ficou em "bom"
   ou "excelente". A mensagem traz o total, as parcelas sem juros, o preço no Pix, a loja e o link.
   Empate de preço: ganha a loja com mais parcelas sem juros.
2. **Achado no Pelando** — post novo de promoção da TV com preço dentro do alvo.
   O preço do post pode ser no Pix ou com cupom: confira o total parcelado sem juros antes de comprar.
3. **Resumo diário** (às 20h) — melhor preço de cada tamanho e quanto falta para o alvo.
   Serve também para saber que o monitor está vivo. Desligue com `RESUMO_DIARIO = False`.

Sem spam: a mesma oferta só é avisada de novo se o preço **cair mais R$ 50**, se passar de
"bom" para "excelente", ou se ela **sumir por 6h e voltar**. Se o envio falhar, tenta de novo
na próxima verificação.

Exemplo de mensagem:
```
🔥 PREÇO EXCELENTE — TV 55"
TCL QD-Mini LED C6K 55"

💳 R$ 2.450,00 em 12x sem juros
     12x de R$ 204,17
💠 No Pix: R$ 2.290,00
🏪 Amazon
🎯 Seu alvo (total sem juros): bom até R$ 2.800,00 · excelente até R$ 2.500,00

🔗 https://www.amazon.com.br/dp/...
```

## 🎮 Como usar

```bash
python monitor_precos.py                   # menu interativo
python monitor_precos.py --buscar          # verifica agora e mostra a tabela
python monitor_precos.py --buscar --tamanho 55
python monitor_precos.py --monitorar       # loop com a janela aberta (intervalo automático)
python monitor_precos.py --black-friday    # loop a cada 15 min, independente da data
python monitor_precos.py --exportar-csv historico.csv
```

## ⚙️ Ajustes (`config.py`)

| Configuração | Padrão | O que faz |
|--------------|--------|-----------|
| `alvo_bom` / `alvo_excelente` | ver tabela acima | Preços-alvo (total sem juros), por tamanho |
| `TAMANHOS_ALERTA` | `["50", "55", "65"]` | Tamanhos que mandam alerta (tire os que não quer) |
| `PARCELAS_MINIMAS` | `10` | Ofertas com menos parcelas sem juros não geram alerta |
| `QUEDA_MINIMA_REALERTA` | `50` | Queda (R$) para avisar de novo a mesma oferta |
| `RESUMO_DIARIO` / `RESUMO_DIARIO_HORA` | `True` / `20` | Resumo diário e horário |
| `INTERVALO_NORMAL` / `INTERVALO_BLACK_FRIDAY` | `60` / `15` | Minutos entre verificações |

## 📁 Estrutura do Projeto

```
c6k-tcl/
├── monitor_precos.py        ← Script principal (rode este!)
├── config.py                ← Preços-alvo e configurações
├── alertas.py               ← Regras de alerta + WhatsApp/ntfy/Telegram
├── historico.py             ← Histórico de preços
├── agendar_tarefa.ps1       ← Cria/remove a tarefa no Agendador do Windows
├── .github/workflows/
│   └── monitor.yml          ← Roda na nuvem do GitHub (horários e Secrets)
├── requirements.txt
├── scrapers/
│   ├── base.py              ← Classe base, formato R$, leitura de parcelas
│   ├── zoom.py              ← Zoom (Magalu, Fast Shop...)
│   ├── kabum.py
│   ├── amazon_br.py
│   ├── pelando.py           ← Promoções da comunidade
│   └── (desativados: mercadolivre, magalu, casasbahia, google_shopping, buscape)
├── historico/
│   ├── precos_cartao.json   ← Histórico (total parcelado sem juros)
│   ├── estado_alertas.json  ← O que já foi avisado
│   ├── monitor.log          ← Log da verificação automática
│   └── precos.json          ← Histórico antigo (era preço de Pix — não é mais usado)
├── notificacoes_config.json ← Seus canais (gerado na configuração)
└── backup_original_2026-10-06/  ← Cópia do projeto antes desta versão
```

## ⚠️ Observações

- Os sites podem mudar o layout a qualquer momento. Se uma fonte quebrar, o resumo diário
  avisa ("Fontes com erro") e o log mostra o erro.
- A Amazon às vezes responde "Algo deu errado" (bloqueio leve); o programa espera e tenta de novo.
- Ofertas que a loja não informa o parcelamento aparecem no fim da tabela ("não informado"),
  porque o preço delas pode ser o do Pix.
- O CallMeBot é um serviço gratuito de terceiros, só para uso pessoal. Se ele falhar,
  o ntfy é um bom canal reserva.
