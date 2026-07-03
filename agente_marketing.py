#!/usr/bin/env python3
"""
Agente de Marketing — 135 SNEAKERS
Multimarcas premium masculina | Brasília, Sudoeste | @135store (~45K seguidores)
Roda com: python agente_marketing.py
"""

import os
import json
import requests
from datetime import datetime, timedelta
from dotenv import load_dotenv

load_dotenv()

WINDSOR_API_KEY = os.getenv("WINDSOR_API_KEY", "")
WINDSOR_BASE    = "https://api.windsor.ai/v1/data"

PERFIS_MONITORAR = {
    "regionais":             ["quadrahomem", "leone.cuordileone", "usedane_se"],
    "lojas_nacionais":       ["tailorsmind", "newold.oficial", "stefanostore",
                              "riquinhostore", "dmzoficial", "adamantostore",
                              "clubedasmarcas"],
    "influencers_nacionais": ["balbiguga", "patrickmunozz", "victoreis92",
                              "soutiagoleite", "modamasculina", "lucasmantellato"],
    "influencers_internacionais": ["whatmyboyfriendwore", "kinshukwearss",
                                   "david.james.elliot", "williamjwade"],
}

TODOS_PERFIS = [p for lista in PERFIS_MONITORAR.values() for p in lista]

# ─────────────────────────────────────────────────────────────────────────────
# 1. MÉTRICAS INSTAGRAM (Windsor.ai)
# ─────────────────────────────────────────────────────────────────────────────

def buscar_metricas_instagram() -> dict:
    """
    Chama a API do Windsor.ai e retorna métricas dos últimos 7 dias
    + top 5 posts por engajamento dos últimos 30 dias.
    """
    hoje     = datetime.today()
    d30_atras = (hoje - timedelta(days=30)).strftime("%Y-%m-%d")
    hoje_str  = hoje.strftime("%Y-%m-%d")

    params = {
        "api_key":   WINDSOR_API_KEY,
        "connector": "instagram",
        "fields":    ("date,reach_1d,total_interactions,likes,saves,shares,"
                      "views,follower_count_1d,media_type,media_caption,"
                      "media_reach,media_engagement,media_permalink"),
        "date_from": d30_atras,
        "date_to":   hoje_str,
    }

    print("  → Chamando Windsor.ai / Instagram…")

    try:
        resp = requests.get(WINDSOR_BASE, params=params, timeout=30)
        resp.raise_for_status()
        dados = resp.json().get("data", [])
    except Exception as e:
        print(f"  ⚠  Erro na API Windsor.ai: {e}")
        dados = []

    # Últimos 7 dias
    sete_dias_atras = hoje - timedelta(days=7)
    recentes = [d for d in dados
                if d.get("date", "") >= sete_dias_atras.strftime("%Y-%m-%d")]

    def soma(campo):
        return sum(int(d.get(campo, 0) or 0) for d in recentes)

    metricas_7d = {
        "alcance_total":       soma("reach_1d"),
        "views_total":         soma("views"),
        "interacoes_total":    soma("total_interactions"),
        "likes_total":         soma("likes"),
        "saves_total":         soma("saves"),
        "shares_total":        soma("shares"),
        "novos_seguidores":    soma("follower_count_1d"),
        "periodo":             f"{sete_dias_atras.strftime('%d/%m')} – {hoje.strftime('%d/%m/%Y')}",
    }

    # Top 5 posts por engajamento (30 dias)
    posts_com_media = [
        d for d in dados
        if d.get("media_type") and d.get("media_permalink")
    ]
    posts_ordenados = sorted(
        posts_com_media,
        key=lambda x: int(x.get("media_engagement", 0) or 0),
        reverse=True
    )[:5]

    top_posts = []
    for p in posts_ordenados:
        top_posts.append({
            "data":       p.get("date", "—"),
            "tipo":       p.get("media_type", "—"),
            "engajamento": p.get("media_engagement", 0),
            "alcance":    p.get("media_reach", 0),
            "caption":    (p.get("media_caption") or "")[:120],
            "link":       p.get("media_permalink", "—"),
        })

    # Padrão por tipo de conteúdo
    tipos: dict = {}
    for d in dados:
        t = d.get("media_type", "OUTRO")
        if t not in tipos:
            tipos[t] = {"count": 0, "engajamento": 0}
        tipos[t]["count"] += 1
        tipos[t]["engajamento"] += int(d.get("media_engagement", 0) or 0)

    tipo_ordenado = sorted(tipos.items(),
                           key=lambda x: x[1]["engajamento"], reverse=True)
    melhor_tipo = tipo_ordenado[0][0] if tipo_ordenado else "CARROSSEL"

    return {
        "metricas_7d":    metricas_7d,
        "top_posts":      top_posts,
        "padrao_tipo":    tipo_ordenado,
        "melhor_tipo":    melhor_tipo,
    }


# ─────────────────────────────────────────────────────────────────────────────
# 2. REFERÊNCIAS — PERFIS CONCORRENTES / INSPIRAÇÃO (Playwright)
# ─────────────────────────────────────────────────────────────────────────────

def buscar_referencias_perfis() -> dict:
    """
    Acessa os 6 posts mais recentes de cada perfil monitorado via Playwright.
    Captura: tipo de post, primeiras palavras da legenda e likes (quando visíveis).
    Perfis que exigem login são pulados e registrados em log.
    """
    from playwright.sync_api import sync_playwright, TimeoutError as PWTimeout

    resultados  = {}
    perfis_skip = []

    print("  → Abrindo navegador (Playwright)…")

    with sync_playwright() as pw:
        browser = pw.chromium.launch(headless=True)
        context = browser.new_context(
            user_agent=(
                "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) "
                "AppleWebKit/537.36 (KHTML, like Gecko) "
                "Chrome/124.0.0.0 Safari/537.36"
            ),
            viewport={"width": 1280, "height": 900},
            locale="pt-BR",
        )
        page = context.new_page()

        for perfil in TODOS_PERFIS:
            url = f"https://www.instagram.com/{perfil}/"
            print(f"    • @{perfil}…", end=" ", flush=True)
            posts_perfil = []

            try:
                page.goto(url, timeout=20_000, wait_until="domcontentloaded")
                page.wait_for_timeout(3_000)

                # Detecta tela de login
                if page.query_selector("input[name='username']"):
                    print("login exigido — pulando")
                    perfis_skip.append(perfil)
                    continue

                # Coleta links dos posts
                links = page.eval_on_selector_all(
                    "article a[href*='/p/'], article a[href*='/reel/']",
                    "els => els.slice(0,6).map(e => e.href)"
                )
                if not links:
                    links = page.eval_on_selector_all(
                        "a[href*='/p/'], a[href*='/reel/']",
                        "els => [...new Set(els.map(e=>e.href))].slice(0,6)"
                    )

                for link in links[:6]:
                    try:
                        page.goto(link, timeout=15_000,
                                  wait_until="domcontentloaded")
                        page.wait_for_timeout(2_000)

                        # Tipo de post
                        tipo = "IMAGEM"
                        if "/reel/" in link:
                            tipo = "REEL"
                        elif page.query_selector("[aria-label='Carrossel']"):
                            tipo = "CARROSSEL"

                        # Caption
                        caption_el = page.query_selector(
                            "h1._aacl, div._a9zs span, article header ~ div span"
                        )
                        caption = ""
                        if caption_el:
                            caption = (caption_el.inner_text() or "")[:100]

                        # Likes
                        likes_el = page.query_selector(
                            "section span[class*='x1lliihq']:has-text('curtida'), "
                            "a[href*='liked_by'] span"
                        )
                        likes = likes_el.inner_text() if likes_el else "—"

                        posts_perfil.append({
                            "tipo": tipo,
                            "caption_inicio": caption[:80],
                            "likes": likes,
                            "link": link,
                        })
                    except PWTimeout:
                        pass
                    except Exception:
                        pass

                print(f"{len(posts_perfil)} posts")
                resultados[perfil] = posts_perfil

            except PWTimeout:
                print("timeout — pulando")
                perfis_skip.append(perfil)
            except Exception as e:
                print(f"erro ({e}) — pulando")
                perfis_skip.append(perfil)

        browser.close()

    # ── Resumo: 3 temas/formatos mais recorrentes ──────────────────────────
    contagem_tipos: dict = {}
    for posts in resultados.values():
        for p in posts:
            t = p["tipo"]
            contagem_tipos[t] = contagem_tipos.get(t, 0) + 1

    temas_recorrentes = sorted(contagem_tipos.items(),
                               key=lambda x: x[1], reverse=True)[:3]

    return {
        "perfis":             resultados,
        "perfis_pulados":     perfis_skip,
        "temas_recorrentes":  temas_recorrentes,
    }


# ─────────────────────────────────────────────────────────────────────────────
# 3. TENDÊNCIAS (Playwright — Hypebeast + Google Trends BR)
# ─────────────────────────────────────────────────────────────────────────────

def buscar_tendencias() -> dict:
    """
    Scrapa Hypebeast (fashion) e Google Trends BR para os termos-chave.
    """
    from playwright.sync_api import sync_playwright, TimeoutError as PWTimeout

    artigos_hypebeast = []
    trends_google     = {}

    TERMOS = ["moda masculina", "sneakers", "streetwear", "look masculino"]

    print("  → Acessando Hypebeast…")

    with sync_playwright() as pw:
        browser = pw.chromium.launch(headless=True)
        context = browser.new_context(
            user_agent=(
                "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
                "AppleWebKit/537.36 (KHTML, like Gecko) "
                "Chrome/124.0.0.0 Safari/537.36"
            ),
            locale="pt-BR",
        )
        page = context.new_page()

        # ── Hypebeast ──────────────────────────────────────────────────────
        try:
            page.goto("https://hypebeast.com/tags/fashion",
                      timeout=25_000, wait_until="domcontentloaded")
            page.wait_for_timeout(3_000)

            titulos = page.eval_on_selector_all(
                "h3, h2, .post-title, article header",
                "els => els.slice(0,10).map(e => e.innerText.trim())"
            )
            artigos_hypebeast = [t for t in titulos if len(t) > 10][:5]
            print(f"    → {len(artigos_hypebeast)} artigos capturados")
        except Exception as e:
            print(f"    ⚠ Hypebeast erro: {e}")

        # ── Google Trends BR ───────────────────────────────────────────────
        print("  → Acessando Google Trends BR…")
        for termo in TERMOS:
            termo_enc = termo.replace(" ", "%20")
            url_gt = (
                f"https://trends.google.com.br/trends/explore"
                f"?q={termo_enc}&geo=BR&hl=pt-BR"
            )
            try:
                page.goto(url_gt, timeout=25_000,
                          wait_until="domcontentloaded")
                page.wait_for_timeout(4_000)

                # Tópicos relacionados
                topicos = page.eval_on_selector_all(
                    ".fe-related-queries .label-text, "
                    "md-list-item .label-text",
                    "els => els.slice(0,5).map(e => e.innerText.trim())"
                )
                trends_google[termo] = topicos if topicos else ["(sem dados)"]
                print(f"    • '{termo}': {topicos[:3]}")
            except Exception as e:
                print(f"    ⚠ Trends '{termo}' erro: {e}")
                trends_google[termo] = ["(erro ao coletar)"]

        browser.close()

    # Consolida lista plana de tendências
    todas_tendencias = list(artigos_hypebeast)
    for t_list in trends_google.values():
        for t in t_list:
            if t not in todas_tendencias and t not in ("(sem dados)", "(erro ao coletar)"):
                todas_tendencias.append(t)

    return {
        "hypebeast_artigos": artigos_hypebeast,
        "google_trends":     trends_google,
        "consolidado":       todas_tendencias[:15],
    }


# ─────────────────────────────────────────────────────────────────────────────
# 4. GERAÇÃO DO CALENDÁRIO EDITORIAL
# ─────────────────────────────────────────────────────────────────────────────

def gerar_calendario(metricas: dict, referencias: dict, tendencias: dict) -> list:
    """
    Gera calendário com 5 posts para os próximos 7 dias.
    Regras obrigatórias:
      - Mín. 2 carrosseis com contexto de vida (lifestyle, não só produto)
      - Mín. 1 reel "escolhas de [pessoa real]"
      - Máx. 2 posts de produto direto
      - Cada post: dia, horário, tipo, tema, legenda completa, hashtags, métrica esperada
    """
    hoje      = datetime.today()
    dias_pt   = ["Segunda", "Terça", "Quarta", "Quinta",
                 "Sexta", "Sábado", "Domingo"]

    # Melhor tipo baseado nos dados
    melhor    = metricas.get("melhor_tipo", "CARROSSEL")
    tendencias_lista = tendencias.get("consolidado", [])
    tendencia1 = tendencias_lista[0] if tendencias_lista else "streetwear"
    tendencia2 = tendencias_lista[1] if len(tendencias_lista) > 1 else "look masculino"

    # Horários de pico — padrão premium masculino Brasília
    # (refinado pelos dados de engajamento quando disponíveis)
    horarios = {
        "Segunda": "18h30",
        "Terça":   "12h00",
        "Quarta":  "19h00",
        "Quinta":  "12h30",
        "Sexta":   "18h00",
        "Sábado":  "11h00",
        "Domingo": "17h00",
    }

    # ── 5 posts distribuídos em 7 dias ────────────────────────────────────
    calendario = [
        {
            "numero":      1,
            "dia_offset":  1,   # amanhã
            "tipo":        "CARROSSEL",
            "categoria":   "lifestyle",
            "tema":        "O café que antecede o estilo",
            "descricao":   (
                "Carrossel de contexto de vida: rotina matinal — café, "
                "mesa limpa, tênis na lateral do frame. Não é sobre o produto; "
                "é sobre quem usa. Última foto: close no sneaker do dia."
            ),
            "legenda": (
                "Antes de qualquer reunião, qualquer decisão — tem o café.\n\n"
                "A manhã dita o tom. O look também.\n\n"
                "Qual é o seu ritual antes de sair?\n\n"
                "📍 Sudoeste, Brasília — Multiplus Shopping\n"
                "🔗 Link na bio"
            ),
            "hashtags": (
                "#135store #EstiloMasculino #MasculinoDeVerdade #ModaMasculinaBrasil "
                "#LifestyleMasculino #SneakersBrasilia #LookDodia #BrasiliaStyle"
            ),
            "metrica_esperada": "Alcance +20% vs. média | Saves alto (lifestyle gera save)",
        },
        {
            "numero":      2,
            "dia_offset":  2,
            "tipo":        "REEL",
            "categoria":   "pessoas reais",
            "tema":        "As escolhas de [cliente real]",
            "descricao":   (
                "Reel curto (30–45s): um cliente ou colaborador mostra "
                "3 peças que ele escolheu + onde usa cada uma. "
                "Abordagem documental, câmera na mão, sem script rígido."
            ),
            "legenda": (
                "Cada homem tem o seu estilo. O nosso papel é só ter o que combina com o dele.\n\n"
                "Esse é o [NOME] — e essas foram as escolhas dele essa semana.\n\n"
                "Qual seria a sua?\n\n"
                "🏬 135 SNEAKERS | Multiplus Shopping — Sudoeste\n"
                "🔗 Link na bio"
            ),
            "hashtags": (
                "#135store #EstiloMasculino #ReelModa #ClienteReal "
                f"#{tendencia1.replace(' ', '')} #HugoBoss #Diesel #Osklen"
            ),
            "metrica_esperada": "Alcance orgânico alto | Compartilhamentos | Novos seguidores",
        },
        {
            "numero":      3,
            "dia_offset":  3,
            "tipo":        "CARROSSEL",
            "categoria":   "lifestyle",
            "tema":        f"Brasília no fim de tarde + {tendencia2}",
            "descricao":   (
                "Carrossel inspiracional: fotos do Sudoeste / lago / pôr do sol em Brasília "
                f"misturadas com looks. Conecta a cidade à identidade da marca. "
                f"Gancho na tendência '{tendencia2}'."
            ),
            "legenda": (
                "Brasília tem essa coisa: a luz do fim de tarde muda tudo.\n\n"
                "O look, o lugar, o momento.\n\n"
                f"Inspiração de hoje: {tendencia2.title()} com a identidade da cidade.\n\n"
                "📍 Sudoeste — onde a gente vive e onde a moda faz sentido\n"
                "🔗 Loja física: Multiplus Shopping"
            ),
            "hashtags": (
                f"#135store #Brasilia #SudoesteBrasilia #{tendencia2.replace(' ','')} "
                "#ModaMasculina #EstiloUrbano #LookMasculino #Sneakers"
            ),
            "metrica_esperada": "Engajamento local alto | Saves | Comentários de geolocalização",
        },
        {
            "numero":      4,
            "dia_offset":  5,
            "tipo":        "IMAGEM",
            "categoria":   "produto direto",
            "tema":        "Drop da semana — produto único em destaque",
            "descricao":   (
                "Post de produto direto com enquadramento editorial limpo. "
                "Storytelling da peça: origem da marca (ex: Hugo Boss, Veja, Armani), "
                "contexto de uso. Máximo 1 produto por frame."
            ),
            "legenda": (
                "Algumas peças não precisam de legenda.\n\n"
                "Mas a gente conta a história de qualquer jeito.\n\n"
                "[MARCA] — [NOME DO PRODUTO]\n"
                "Disponível na loja. Unidades limitadas.\n\n"
                "📍 Multiplus Shopping, Sudoeste — Brasília\n"
                "📲 Chama no Direct ou passa aqui"
            ),
            "hashtags": (
                "#135store #[Marca] #DropDaSemana #ModaMasculinaBrasil "
                "#SneakersBR #EstiloMasculino #LookMasculino #Brasilia"
            ),
            "metrica_esperada": "CTAs (direct/link) | Saves de produto | Visualizações de perfil",
        },
        {
            "numero":      5,
            "dia_offset":  6,
            "tipo":        melhor if melhor not in ("IMAGEM",) else "CARROSSEL",
            "categoria":   "produto direto",
            "tema":        "Combinação da semana — outfit completo",
            "descricao":   (
                "Post de produto: combinação de 3–5 peças da loja formando um outfit. "
                "Apresentar como curadoria, não catálogo. "
                "Formato carrossel se 'melhor_tipo' for carrossel, caso contrário reel curto."
            ),
            "legenda": (
                "Montar um look não é sobre ter tudo — é sobre escolher certo.\n\n"
                "Curadoria da semana: [DESCREVER PEÇAS]\n\n"
                "Tudo disponível na 135 SNEAKERS.\n"
                "📍 Sudoeste | Multiplus Shopping\n"
                "💬 Conta aqui qual você usaria"
            ),
            "hashtags": (
                "#135store #OutfitDaSemana #CuradoriaDeEstilo #ModaMasculina "
                "#LookCompleto #EstiloMasculino #Brasilia #SneakersBrasilia"
            ),
            "metrica_esperada": "Comentários (pergunta ativa) | Saves | Alcance compartilhado",
        },
    ]

    # Resolve datas reais e horários
    for post in calendario:
        data_post = hoje + timedelta(days=post["dia_offset"])
        dia_nome  = dias_pt[data_post.weekday()]
        post["data"]     = data_post.strftime("%d/%m/%Y")
        post["dia_nome"] = dia_nome
        post["horario"]  = horarios.get(dia_nome, "18h00")
        del post["dia_offset"]

    return calendario


# ─────────────────────────────────────────────────────────────────────────────
# IMPRESSÃO DO RELATÓRIO
# ─────────────────────────────────────────────────────────────────────────────

def imprimir_relatorio(metricas: dict, referencias: dict,
                       tendencias: dict, calendario: list) -> None:
    SEP  = "─" * 65
    SEP2 = "═" * 65

    print(f"\n{SEP2}")
    print("  135 SNEAKERS — RELATÓRIO DE MARKETING DIGITAL")
    print(f"  Gerado em: {datetime.today().strftime('%d/%m/%Y %H:%M')}")
    print(SEP2)

    # ── 1. MÉTRICAS ────────────────────────────────────────────────────────
    print(f"\n📊  MÉTRICAS DA SEMANA  ({metricas['metricas_7d']['periodo']})")
    print(SEP)
    m = metricas["metricas_7d"]
    print(f"  Alcance total   : {m['alcance_total']:,}")
    print(f"  Views totais    : {m['views_total']:,}")
    print(f"  Interações      : {m['interacoes_total']:,}")
    print(f"  Likes           : {m['likes_total']:,}")
    print(f"  Saves           : {m['saves_total']:,}")
    print(f"  Shares          : {m['shares_total']:,}")
    print(f"  Novos seguidores: {m['novos_seguidores']:,}")

    print(f"\n  🏆 Tipo de conteúdo com maior engajamento: {metricas['melhor_tipo']}")

    print(f"\n  Top 5 Posts (últimos 30 dias):")
    for i, p in enumerate(metricas["top_posts"], 1):
        print(f"  {i}. [{p['tipo']}] {p['data']} | ❤ {p['engajamento']} eng.")
        print(f"     \"{p['caption'][:70]}…\"")
        print(f"     🔗 {p['link']}")

    # ── 2. CONCORRENTES ────────────────────────────────────────────────────
    print(f"\n👀  O QUE OS CONCORRENTES ESTÃO FAZENDO")
    print(SEP)
    temas = referencias.get("temas_recorrentes", [])
    print("  3 formatos/temas mais recorrentes nos perfis monitorados:")
    for i, (tipo, qtd) in enumerate(temas, 1):
        print(f"  {i}. {tipo}  ({qtd} posts analisados)")

    skip = referencias.get("perfis_pulados", [])
    if skip:
        print(f"\n  ⚠  Perfis que exigiram login (pulados): {', '.join(['@'+p for p in skip])}")

    total_perfis = len(referencias.get("perfis", {}))
    print(f"\n  ✅ {total_perfis} perfis analisados com sucesso de {len(TODOS_PERFIS)} tentativas")

    # ── 3. TENDÊNCIAS ──────────────────────────────────────────────────────
    print(f"\n🔥  TENDÊNCIAS EM ALTA")
    print(SEP)
    hype = tendencias.get("hypebeast_artigos", [])
    if hype:
        print("  Hypebeast (fashion) — últimos artigos:")
        for a in hype:
            print(f"    • {a}")

    print("\n  Google Trends BR — tópicos relacionados:")
    for termo, topicos in tendencias.get("google_trends", {}).items():
        print(f"    [{termo}]: {' | '.join(topicos[:3])}")

    # ── 4. CALENDÁRIO ──────────────────────────────────────────────────────
    print(f"\n📅  CALENDÁRIO EDITORIAL — PRÓXIMOS 7 DIAS")
    print(SEP)
    for post in calendario:
        print(f"\n  POST {post['numero']}  •  {post['dia_nome']}, {post['data']}  •  {post['horario']}")
        print(f"  Tipo      : {post['tipo']}  [{post['categoria'].upper()}]")
        print(f"  Tema      : {post['tema']}")
        print(f"  Briefing  : {post['descricao']}")
        print(f"\n  📝 LEGENDA SUGERIDA:")
        for linha in post["legenda"].split("\n"):
            print(f"     {linha}")
        print(f"\n  #️⃣  Hashtags: {post['hashtags']}")
        print(f"  📈 Métrica esperada: {post['metrica_esperada']}")
        print(f"  {SEP}")

    print(f"\n{'═'*65}")
    print("  FIM DO RELATÓRIO — 135 SNEAKERS")
    print(f"{'═'*65}\n")


# ─────────────────────────────────────────────────────────────────────────────
# PONTO DE ENTRADA
# ─────────────────────────────────────────────────────────────────────────────

# ─────────────────────────────────────────────────────────────────────────────
# EXPORTAR PDF
# ─────────────────────────────────────────────────────────────────────────────

def _s(texto: str) -> str:
    """Sanitiza texto removendo caracteres fora do range Latin-1 (fpdf Helvetica)."""
    substituicoes = {
        "–": "-", "—": "-", "’": "'", "‘": "'",
        "“": '"', "”": '"', "•": "*", "…": "...",
        "→": "->", "←": "<-", "é": "e", "ã": "a",
        "ç": "c", "õ": "o", "à": "a", "ê": "e",
        "í": "i", "ú": "u", "ó": "o", "â": "a",
        "ô": "o", "û": "u", "î": "i", "è": "e",
        "ù": "u", "ä": "a", "ö": "o", "ü": "u",
        "É": "E", "Ã": "A", "Ç": "C", "Õ": "O",
        "À": "A", "Ê": "E", "Í": "I", "Ú": "U",
        "Ó": "O", "Â": "A", "Ô": "O",
    }
    for orig, rep in substituicoes.items():
        texto = texto.replace(orig, rep)
    return texto.encode("latin-1", errors="ignore").decode("latin-1")


def exportar_pdf(metricas: dict, referencias: dict,
                 tendencias: dict, calendario: list) -> str:
    from fpdf import FPDF

    data_str  = datetime.today().strftime("%Y-%m-%d")
    nome_pdf  = f"relatorio_135_{data_str}.pdf"

    pdf = FPDF()
    pdf.set_auto_page_break(auto=True, margin=15)
    pdf.add_page()

    # Cabeçalho
    pdf.set_font("Helvetica", "B", 18)
    pdf.cell(0, 10, "135 SNEAKERS - Relatorio de Marketing", ln=True, align="C")
    pdf.set_font("Helvetica", "", 10)
    pdf.cell(0, 6, f"Gerado em: {datetime.today().strftime('%d/%m/%Y %H:%M')}", ln=True, align="C")
    pdf.ln(6)

    def secao(titulo):
        pdf.set_font("Helvetica", "B", 13)
        pdf.set_fill_color(30, 30, 30)
        pdf.set_text_color(255, 255, 255)
        pdf.cell(0, 8, _s(f"  {titulo}"), ln=True, fill=True)
        pdf.set_text_color(0, 0, 0)
        pdf.ln(3)

    def linha(texto, negrito=False):
        pdf.set_font("Helvetica", "B" if negrito else "", 10)
        pdf.multi_cell(0, 6, _s(str(texto)))

    # 1. Métricas
    secao("📊  MÉTRICAS DA SEMANA")
    m = metricas["metricas_7d"]
    for chave, valor in [
        ("Período",           m["periodo"]),
        ("Alcance total",     f"{m['alcance_total']:,}"),
        ("Views totais",      f"{m['views_total']:,}"),
        ("Interações",        f"{m['interacoes_total']:,}"),
        ("Likes",             f"{m['likes_total']:,}"),
        ("Saves",             f"{m['saves_total']:,}"),
        ("Shares",            f"{m['shares_total']:,}"),
        ("Novos seguidores",  f"{m['novos_seguidores']:,}"),
        ("Melhor tipo",       metricas.get("melhor_tipo", "—")),
    ]:
        linha(f"{chave}: {valor}")

    pdf.ln(4)
    linha("Top 5 Posts (últimos 30 dias):", negrito=True)
    for i, p in enumerate(metricas["top_posts"], 1):
        linha(f"{i}. [{p['tipo']}] {p['data']} | Eng: {p['engajamento']}")
        linha(f"   {p['caption'][:90]}")
        linha(f"   {p['link']}")
    pdf.ln(4)

    # 2. Concorrentes
    secao("👀  O QUE OS CONCORRENTES ESTÃO FAZENDO")
    for i, (tipo, qtd) in enumerate(referencias.get("temas_recorrentes", []), 1):
        linha(f"{i}. {tipo} — {qtd} posts analisados")
    pulados = referencias.get("perfis_pulados", [])
    if pulados:
        linha(f"Perfis que exigiram login: {', '.join(['@'+p for p in pulados])}")
    pdf.ln(4)

    # 3. Tendências
    secao("🔥  TENDÊNCIAS EM ALTA")
    for a in tendencias.get("hypebeast_artigos", []):
        linha(f"• {a}")
    pdf.ln(2)
    for termo, topicos in tendencias.get("google_trends", {}).items():
        linha(f"[{termo}]: {' | '.join(topicos[:3])}")
    pdf.ln(4)

    # 4. Calendário
    secao("📅  CALENDÁRIO EDITORIAL — PRÓXIMOS 7 DIAS")
    for post in calendario:
        pdf.set_font("Helvetica", "B", 11)
        pdf.cell(0, 7,
                 _s(f"POST {post['numero']}  |  {post['dia_nome']}, "
                    f"{post['data']}  |  {post['horario']}"),
                 ln=True)
        linha(f"Tipo: {post['tipo']}  |  {post['categoria'].upper()}")
        linha(f"Tema: {post['tema']}")
        linha(f"Briefing: {post['descricao']}")
        pdf.ln(2)
        linha("LEGENDA:", negrito=True)
        linha(post["legenda"])
        pdf.ln(2)
        linha(f"Hashtags: {post['hashtags']}")
        linha(f"Métrica esperada: {post['metrica_esperada']}")
        pdf.ln(5)

    pdf.output(nome_pdf)
    print(f"\n✅  PDF gerado: {nome_pdf}")
    return nome_pdf


# ─────────────────────────────────────────────────────────────────────────────
# UPLOAD GOOGLE DRIVE
# ─────────────────────────────────────────────────────────────────────────────

def salvar_no_drive(pdf_path: str) -> str:
    """
    Faz upload do PDF para o Google Drive usando uma Service Account.
    Requer variável de ambiente GOOGLE_CREDENTIALS (JSON da service account)
    e GOOGLE_DRIVE_FOLDER_ID (ID da pasta de destino).
    """
    import json
    from google.oauth2 import service_account
    from googleapiclient.discovery import build
    from googleapiclient.http import MediaFileUpload

    creds_json    = os.getenv("GOOGLE_CREDENTIALS", "")
    folder_id     = os.getenv("GOOGLE_DRIVE_FOLDER_ID", "")

    if not creds_json or not folder_id:
        print("⚠  GOOGLE_CREDENTIALS ou GOOGLE_DRIVE_FOLDER_ID não configurados — pulando upload.")
        return ""

    try:
        info  = json.loads(creds_json)
        creds = service_account.Credentials.from_service_account_info(
            info, scopes=["https://www.googleapis.com/auth/drive.file"]
        )
        service = build("drive", "v3", credentials=creds)

        file_meta = {
            "name":    os.path.basename(pdf_path),
            "parents": [folder_id],
        }
        media = MediaFileUpload(pdf_path, mimetype="application/pdf")
        f = service.files().create(
            body=file_meta, media_body=media, fields="id,webViewLink"
        ).execute()

        link = f.get("webViewLink", "")
        print(f"✅  PDF salvo no Google Drive: {link}")
        return link
    except Exception as e:
        print(f"⚠  Erro ao salvar no Drive: {e}")
        return ""


def main():
    print("\n🚀  Iniciando Agente de Marketing — 135 SNEAKERS\n")

    if not WINDSOR_API_KEY:
        print("⚠  WINDSOR_API_KEY não encontrada no .env — métricas serão vazias.\n")

    print("🔍  [1/4] Buscando métricas do Instagram (Windsor.ai)…")
    metricas = buscar_metricas_instagram()

    print("\n👀  [2/4] Analisando perfis de referência (Playwright)…")
    referencias = buscar_referencias_perfis()

    print("\n🔥  [3/4] Mapeando tendências (Hypebeast + Google Trends)…")
    tendencias = buscar_tendencias()

    print("\n📅  [4/4] Gerando calendário editorial…")
    calendario = gerar_calendario(metricas, referencias, tendencias)

    imprimir_relatorio(metricas, referencias, tendencias, calendario)

    print("\n📄  [5/5] Exportando PDF e enviando ao Google Drive…")
    pdf_path = exportar_pdf(metricas, referencias, tendencias, calendario)
    salvar_no_drive(pdf_path)


if __name__ == "__main__":
    main()
