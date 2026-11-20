import os, re, json, time, random, html, requests
from datetime import datetime, timezone, timedelta
import matplotlib.pyplot as plt
from google import genai

TZ_ART = timezone(timedelta(hours=-3))
TELEGRAM_BOT_TOKEN = (os.getenv("TELEGRAM_BOT_TOKEN") or os.getenv("TELEGRAM_TOKEN") or "").strip()
TELEGRAM_CHAT_ID = (os.getenv("TELEGRAM_CHAT_ID") or os.getenv("CHAT_ID") or "").strip()
TELEGRAM_TOPIC_ID = (os.getenv("TOPIC_ID_CENTRAL") or "1").strip()
GEMINI_API_KEY = (os.getenv("GEMINI_API_KEY") or "").strip()
BASE_URL_NETLIFY = "https://gregarious-frangollo-0346c5.netlify.app"
ARCHIVO_MEMORIA = "ultimas_perlas.json"
PRECIO_MAX_SILENCIOSA = 5.00

def ahora_art():
    return datetime.now(TZ_ART)

def cargar_memoria_perlas():
    if os.path.exists(ARCHIVO_MEMORIA):
        try:
            with open(ARCHIVO_MEMORIA, 'r', encoding='utf-8') as f:
                return json.load(f)
        except Exception:
            return []
    return []

def guardar_memoria_perlas(historial_reportes):
    try:
        with open(ARCHIVO_MEMORIA, 'w', encoding='utf-8') as f:
            json.dump(historial_reportes[-2:], f, indent=2)
    except Exception as e:
        print(f"Error memoria: {e}")

def crear_sesion_binance():
    s = requests.Session()
    s.headers.update({"User-Agent": "Mozilla/5.0", "Accept": "application/json", "Cache-Control": "no-cache"})
    return s

def obtener_datos_completos_binance(session):
    spot_activos, tickers_spot, vol_futuros = set(), [], {}

    for url in ["https://api.binance.com/api/v3/exchangeInfo", "https://data-api.binance.vision/api/v3/exchangeInfo"]:
        try:
            res = session.get(url, timeout=12)
            if res.status_code == 200:
                spot_activos = {s['symbol'] for s in res.json().get('symbols', []) if s.get('status') == 'TRADING' and s.get('quoteAsset') == 'USDT'}
                if spot_activos: break
        except Exception:
            continue

    for url in ["https://api.binance.com/api/v3/ticker/24hr", "https://data-api.binance.vision/api/v3/ticker/24hr"]:
        try:
            r = session.get(url, timeout=15)
            if r.status_code == 200 and isinstance(r.json(), list) and r.json():
                tickers_spot = r.json()
                break
        except Exception:
            continue

    # Consulta volumen de Futuros USD-M para igualar el ranking "Mayor volumen" de Binance Mercados
    try:
        rf = session.get("https://fapi.binance.com/fapi/v1/ticker/24hr", timeout=10)
        if rf.status_code == 200 and isinstance(rf.json(), list):
            for item in rf.json():
                sym = item.get('symbol', '')
                if sym.endswith('USDT'):
                    vol_futuros[sym] = float(item.get('quoteVolume', 0))
    except Exception:
        pass

    return spot_activos, tickers_spot, vol_futuros

def formatear_precio(p):
    if p is None or p <= 0: return "$0.00"
    if p >= 100: return f"${p:,.2f}"
    if p >= 1.0: return f"${p:.4f}"
    if p >= 0.01: return f"${p:.5f}"
    if p >= 0.0001: return f"${p:.6f}"
    return f"${p:.8f}"

def generar_barra_progreso(cambio, tipo_bloque=""):
    if tipo_bloque == "acumulacion_24h": return "🟨🟨🟨⬜⬜"
    if tipo_bloque == "silenciosa": return "💎💎💎💎⬜"
    if cambio >= 50: return "🟢🟢🟢🟢🟢"
    if cambio >= 25: return "🟢🟢🟢🟢⬜"
    if cambio >= 15: return "🟢🟢🟢⬜⬜"
    if cambio >= 5: return "🟢🟢⬜⬜⬜"
    if cambio > 0: return "🟢⬜⬜⬜⬜"
    if cambio > -5: return "🟥🟥⬜⬜⬜"
    if cambio > -12: return "🟥🟥🟥⬜⬜"
    if cambio > -20: return "🟥🟥🟥🟥⬜"
    return "🟥🟥🟥🟥🟥"

def seleccionar_silenciosas_con_gemini(candidatas, historial_previo):
    bloqueados = {item for rep in historial_previo for item in rep}
    pool = [c for c in candidatas if c['symbol'] not in bloqueados]
    if len(pool) < 7:
        pool = candidatas
    pool_ordenado = sorted(pool, key=lambda x: x['factor_vol'] * (0.5 + x['pos_rango']), reverse=True)[:22]
    if not GEMINI_API_KEY or not pool_ordenado:
        return pool_ordenado[:7]
    try:
        client = genai.Client(api_key=GEMINI_API_KEY)
        resumen = [f"{c['base_asset']}: precio={formatear_precio(c['lastPrice_f'])}, var24h={c['pct_24h']:+.2f}%, posRango={int(c['pos_rango']*100)}%, volUSDT={int(c['quoteVolume_f']):,}, presion=x{c['factor_vol']:.1f}" for c in pool_ordenado]
        prompt = "Analista cuantitativo Binance Spot. De estas altcoins (< $5 USD, en verde, sin stablecoins), elige exactamente los 7 tickers con mejor acumulación silenciosa alcista (liquidez y sostén en zona alta). Devuelve SOLO los 7 tickers separados por coma (ej: ARB,OP,SEI,TIA,IMX,PYTH,FET):\n" + "\n".join(resumen)
        for mod in ['gemini-2.5-flash', 'gemini-1.5-flash']:
            try:
                res = client.models.generate_content(model=mod, contents=prompt)
                if res and res.text:
                    elegidos = [x.strip().upper().replace("USDT", "") for x in res.text.split(",")]
                    mapa = {c['base_asset']: c for c in pool_ordenado}
                    sel = [mapa[s] for s in elegidos if s in mapa]
                    for c in pool_ordenado:
                        if len(sel) >= 7: break
                        if c not in sel: sel.append(c)
                    return sel[:7]
            except Exception:
                continue
    except Exception as e:
        print(f"⚠️ Fallback Gemini: {e}")
    return pool_ordenado[:7]

def preparar_datos(tickers_spot, spot_activos, vol_futuros):
    todos, web_spot, web_volumen = {}, [], []
    EXCLUIDOS = {'USDT','USDC','FDUSD','DAI','TUSD','USDP','EUR','BUSD','AEUR','EURI','USD1','USDE','RLUSD','RWUSD','XUSD','BFUSD','PAXG','XAUT','U','USDG','USDS','PYUSD','GUSD','SUSD','FRAX','CREAM','EPX','FOR','VGX','WNXM','BOND','LOOM','OAX','MULTI','KP3R','AKRO','BLZ','WRX','SNXXB','MSTRB','GBP','TRY','BRL','ARS'}
    vistos = set()

    for t in tickers_spot:
        sym = t.get('symbol', '')
        if not sym.endswith('USDT') or sym not in spot_activos: continue
        base = sym[:-4]
        if any(x in base for x in ['UP', 'DOWN', 'BULL', 'BEAR']): continue
        try:
            lp, vq_spot, hp, lowp, pct_24h = float(t['lastPrice']), float(t['quoteVolume']), float(t['highPrice']), float(t['lowPrice']), float(t['priceChangePercent'])
            if lp <= 0: continue
            base_24h = (lp / (1.0 + (pct_24h / 100.0))) if pct_24h > -99.9 else float(t.get('openPrice', lp))
            rango = hp - lowp
            vol_total_mercado = vq_spot + vol_futuros.get(sym, 0.0)
            t.update({
                'base_asset': base,
                'base_24h_f': base_24h,
                'lastPrice_f': lp,
                'pct_24h': pct_24h,
                'quoteVolume_f': vq_spot,
                'vol_mercado_f': vol_total_mercado,
                'highPrice_f': hp,
                'lowPrice_f': lowp,
                'pct_rango': (rango / lp) * 100,
                'pos_rango': ((lp - lowp) / rango) if rango > 0 else 0.5
            })
            todos[sym] = t
            vistos.add(sym)
            if base not in EXCLUIDOS:
                if vq_spot >= 900_000:
                    web_spot.append(t)
                if vol_total_mercado >= 1_000_000:
                    web_volumen.append(t)
        except Exception:
            continue

    # Añade activos líderes que operan fuerte en Futuros de Binance (ej. HYPE) para espejar "Mayor volumen"
    if vol_futuros:
        try:
            rf = requests.get("https://fapi.binance.com/fapi/v1/ticker/24hr", timeout=10).json()
            for item in rf:
                sym = item.get('symbol', '')
                if sym.endswith('USDT') and sym not in vistos:
                    base = sym[:-4]
                    if base in EXCLUIDOS: continue
                    lp = float(item.get('lastPrice', 0))
                    pct_24h = float(item.get('priceChangePercent', 0))
                    vq = float(item.get('quoteVolume', 0))
                    if lp > 0 and vq >= 50_000_000:
                        base_24h = (lp / (1.0 + (pct_24h / 100.0))) if pct_24h > -99.9 else lp
                        web_volumen.append({
                            'symbol': sym, 'base_asset': base, 'base_24h_f': base_24h,
                            'lastPrice_f': lp, 'pct_24h': pct_24h, 'quoteVolume_f': vq,
                            'vol_mercado_f': vq, 'highPrice_f': float(item.get('highPrice', lp)),
                            'lowPrice_f': float(item.get('lowPrice', lp)), 'pct_rango': 2.0, 'pos_rango': 0.5
                        })
        except Exception:
            pass

    ganadoras = sorted([t for t in web_spot if t['pct_24h'] > 0], key=lambda x: x['pct_24h'], reverse=True)[:7]
    perdedoras = sorted([t for t in web_spot if t['pct_24h'] < 0], key=lambda x: x['pct_24h'])[:7]
    acum_24h = sorted(web_volumen, key=lambda x: x['vol_mercado_f'], reverse=True)[:7]

    hist = cargar_memoria_perlas()
    cand = []
    for t in web_spot:
        if not re.match(r'^[A-Z0-9]+$', t['base_asset']): continue
        if t['lastPrice_f'] < PRECIO_MAX_SILENCIOSA and 0.40 <= t['pct_24h'] <= 7.50 and t['pct_rango'] >= 1.20 and t['pos_rango'] >= 0.50 and t['quoteVolume_f'] >= 1_500_000:
            vol_m = min(t['quoteVolume_f'] / 1_000_000, 60.0)
            t['factor_vol'] = max(1.3, round(1.2 + ((vol_m / max(t['pct_rango'], 1.0)) * 0.25), 1))
            cand.append(t)
    if len(cand) < 7:
        for t in web_spot:
            if not re.match(r'^[A-Z0-9]+$', t['base_asset']): continue
            if t not in cand and t['lastPrice_f'] < PRECIO_MAX_SILENCIOSA and 0.15 <= t['pct_24h'] <= 9.0 and t['pct_rango'] >= 1.0 and t['quoteVolume_f'] >= 1_000_000:
                vol_m = min(t['quoteVolume_f'] / 1_000_000, 60.0)
                t['factor_vol'] = max(1.2, round(1.1 + ((vol_m / max(t['pct_rango'], 1.0)) * 0.25), 1))
                cand.append(t)

    silenciosa = seleccionar_silenciosas_con_gemini(cand, hist)
    guardar_memoria_perlas(hist + [[t['symbol'] for t in silenciosa]])
    favoritas = [todos[f"{s}USDT"] for s in ['QI', 'TUT', 'NEIRO', 'LUNC', 'BANK'] if f"{s}USDT" in todos]
    return ganadoras, perdedoras, acum_24h, silenciosa, favoritas

def generar_grafico_tema(items, titulo, color, filename):
    ordenados = sorted(items, key=lambda x: x['pct_24h'])
    sims = [i['base_asset'] for i in ordenados]
    cambios = [i['pct_24h'] for i in ordenados]
    fig, ax = plt.subplots(figsize=(8, 4.5), facecolor='#0b132b')
    ax.set_facecolor('#0b132b')
    bars = ax.bar(sims, cambios, color=color, width=0.5, zorder=3)
    ax.grid(True, color='#1e293b', linewidth=0.8, zorder=1)
    for s in ['top', 'right', 'left', 'bottom']: ax.spines[s].set_visible(False)
    ax.tick_params(left=False, labelleft=False, bottom=False)
    ax.tick_params(axis='x', colors='white', labelsize=10)
    for bar, sim, c in zip(bars, sims, cambios):
        yv, xv = bar.get_height(), bar.get_x() + bar.get_width() / 2.0
        off = 2.5 if yv >= 0 else -5.5
        ax.text(xv, yv + off, f"{c:+.2f}%", ha='center', va='bottom' if yv >= 0 else 'top', color=color, fontweight='bold', fontsize=9)
        ax.plot(xv, yv + (1.2 if yv >= 0 else -1.2), marker='o', markersize=18, markerfacecolor='#0f172a', markeredgecolor=color, markeredgewidth=1.5, zorder=4)
        etiqueta_circulo = sim[:5] if re.match(r'^[A-Z0-9]+$', sim) else sim[:2]
        ax.text(xv, yv + (1.2 if yv >= 0 else -1.2), etiqueta_circulo, ha='center', va='center', color='white', fontsize=7, fontweight='bold', zorder=5)
    plt.title(titulo, loc='left', color='#ffab00', fontsize=12, fontweight='bold', pad=12)
    ax.text(0.0, 1.02, f"Fecha: {ahora_art().strftime('%Y-%m-%d %H:%M ART')}", transform=ax.transAxes, color='#94a3b8', fontsize=8)
    plt.tight_layout()
    plt.savefig(filename, dpi=300, facecolor=fig.get_facecolor())
    plt.close()

def enviar_foto_y_detalle(image_path, texto):
    if not TELEGRAM_BOT_TOKEN or not TELEGRAM_CHAT_ID: return
    url = f"https://api.telegram.org/bot{TELEGRAM_BOT_TOKEN}"
    tid = int(TELEGRAM_TOPIC_ID) if TELEGRAM_TOPIC_ID.isdigit() else None
    cabe = len(texto) <= 1020
    for intento in range(3):
        try:
            pf = {"chat_id": TELEGRAM_CHAT_ID}
            if tid: pf["message_thread_id"] = tid
            if cabe: pf.update({"caption": texto, "parse_mode": "HTML"})
            with open(image_path, 'rb') as ph:
                res = requests.post(f"{url}/sendPhoto", data=pf, files={"photo": ph}, timeout=20).json()
                if not res.get("ok") and "thread not found" in str(res.get("description", "")).lower():
                    pf.pop("message_thread_id", None)
                    ph.seek(0)
                    res = requests.post(f"{url}/sendPhoto", data=pf, files={"photo": ph}, timeout=20).json()
            if res.get("ok"):
                if not cabe:
                    pm = {"chat_id": TELEGRAM_CHAT_ID, "text": texto, "parse_mode": "HTML", "disable_web_page_preview": True}
                    if tid: pm["message_thread_id"] = tid
                    rm = requests.post(f"{url}/sendMessage", json=pm, timeout=15).json()
                    if not rm.get("ok") and "thread not found" in str(rm.get("description", "")).lower():
                        pm.pop("message_thread_id", None)
                        requests.post(f"{url}/sendMessage", json=pm, timeout=15)
                return
        except Exception as e:
            print(f"⚠️ Error envío: {e}")
        time.sleep(3)

def procesar_bloque(num, titulo, icono, items, color, fname, tipo=""):
    if not items: return
    generar_grafico_tema(items, f"{icono} {titulo.upper()} • Ranking 24h", color, fname)
    txt = f"🧠 <b>CENTRAL DE INTELIGENCIA DE MERCADO ({num}/5)</b>\n{icono} <b>{num}. {html.escape(titulo.upper())} (Detalle)</b>\n📅 Fecha: <code>{ahora_art().strftime('%Y-%m-%d %H:%M ART')}</code>\n\n"
    for it in items:
        sim, c = it['base_asset'], it['pct_24h']
        uid = int(time.time() * 1000) + random.randint(1, 99999)
        u_ia = f"{BASE_URL_NETLIFY}/?coin={sim}&price={it['lastPrice_f']}&change={c:.2f}&high={it['highPrice_f']}&low={it['lowPrice_f']}&v={sim}_{uid}"
        u_tr = f"https://www.binance.com/es/trade/{sim}_USDT"
        extra = f" <i>[IA Gemini • Presión x{it.get('factor_vol', 1.3):.1f}]</i>" if tipo == "silenciosa" else ""
        txt += f"• <b>{sim}</b> | Base (0%): <code>{formatear_precio(it['base_24h_f'])}</code> ➔ Actual: <code>{formatear_precio(it['lastPrice_f'])}</code> | <b>{c:+.2f}%</b>\n{generar_barra_progreso(c, tipo)}{extra}\n└ <a href=\"{html.escape(u_ia)}\">📊 Resumen IA</a> | <a href=\"{html.escape(u_tr)}\">🔶 Tradear</a>\n\n"
    enviar_foto_y_detalle(fname, txt.strip())
    time.sleep(2)

if __name__ == "__main__":
    print(f"🚀 INICIANDO CENTRAL DE INTELIGENCIA ({ahora_art().strftime('%H:%M:%S')} ART)...")
    s = crear_sesion_binance()
    activos, datos_spot, vol_fut = obtener_datos_completos_binance(s)
    if datos_spot and activos:
        g, p, a24, sil, fav = preparar_datos(datos_spot, activos, vol_fut)
        procesar_bloque(1, "TOP 7 GANADORAS", "🚀", g, "#00c853", "grafico_ganadoras.png")
        procesar_bloque(2, "TOP 7 PERDEDORAS", "📉", p, "#f6465d", "grafico_perdedoras.png")
        procesar_bloque(3, "TOP 7 ACUMULACION 24H", "💎", a24, "#ffab00", "grafico_acumulacion_24h.png", "acumulacion_24h")
        procesar_bloque(4, "TOP 7 ACUMULACION SILENCIOSA (IA)", "🕵️‍♂️", sil, "#00bcd4", "grafico_silenciosa.png", "silenciosa")
        procesar_bloque(5, "TUS 5 FAVORITAS", "⭐", fav, "#3861fb", "grafico_favoritas.png")
        print("🎉 ¡Los 5 bloques se enviaron correctamente!")
    else:
        print("❌ ERROR: Sin datos de Binance.")

# FIN BOT CRIPTO
