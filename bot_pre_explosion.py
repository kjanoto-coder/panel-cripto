if __name__ == "__main__":
    print("🔥 EJECUTANDO ESCÁNER TÁCTICO DE 15 PERLAS...")
    session = crear_sesion_binance()
    simbolos_activos = obtener_simbolos_spot_activos(session)
    datos = obtener_datos_binance(session)
    
    if datos and len(simbolos_activos) > 0:
        historial = cargar_historial()
        matriz_15_perlas, total_analizadas, historial = motor_ia_seleccion_tactica(datos, simbolos_activos, historial)
        
        if len(matriz_15_perlas) > 0:
            filename = generar_grafico_matriz(matriz_15_perlas)
            dictamen_ia = generar_dictamen_ia(matriz_15_perlas)
            
            # 1. Enviar la foto con un caption corto y seguro
            caption_foto = f"🔥 <b>RADAR TÁCTICO • 15 PERLAS (5 POR COLOR)</b>\n📊 <i>Universo analizado: {total_analizadas} altcoins reales Spot</i>"
            enviar_telegram(filename, caption_foto.strip())
            
            # 2. Construir el mensaje de texto detallado con las 15 perlas y sus enlaces
            mensaje_detalle = f"💡 <b>Dictamen IA / Redes:</b>\n{dictamen_ia}\n\n"
            
            categorias = [
                ("ROJO", "🔴 <b>EXPLOSIÓN INMINENTE (Top 5)</b>"),
                ("AMARILLO", "🟡 <b>CONFIRMACIÓN TÁCTICA (Top 5)</b>"),
                ("VERDE", "🟢 <b>ACUMULACIÓN EN INICIOS (Top 5)</b>")
            ]
            
            for cat_key, cat_title in categorias:
                mensaje_detalle += f"{cat_title}\n"
                for item in matriz_15_perlas:
                    if item['categoria'] == cat_key:
                        sim = item['ticker']
                        precio_str = formatear_precio(item['precio_f'])
                        vol_m = item['vol_f'] / 1_000_000
                        unique_id = int(time.time() * 1000) + random.randint(1, 9999)
                        url_ia = f"{BASE_URL_NETLIFY}/?coin={sim}&price={item['precio_f']}&change={item['cambio_f']}&high={item['high_f']}&low={item['low_f']}&v={sim}_{unique_id}"
                        url_trade = f"https://www.binance.com/es/trade/{sim}_USDT"
                        
                        mensaje_detalle += f"• <b>{sim}</b> ({item['cambio_f']:+.1f}%) | {precio_str} | Rango: {item['pos_liquidez_pct']}%\n"
                        mensaje_detalle += f"  └ <a href=\"{html.escape(url_ia)}\">📊 Resumen IA</a> | <a href=\"{html.escape(url_trade)}\">🔶 Tradear</a>\n"
                mensaje_detalle += "\n"
                
            # Enviar el reporte detallado como mensaje de texto limpio
            enviar_texto_telegram(mensaje_detalle.strip())
            
            # --- CIERRE DIARIO (21:00 hs / 9 PM) ---
            hora_actual = datetime.now().hour
            if hora_actual >= 21 and not historial.get("resumen_enviado_hoy", False):
                monedas_dia = [s.replace('USDT', '') for s in historial.get("resumen_dia", [])]
                if monedas_dia:
                    resumen_texto = f"📋 <b>RESUMEN DIARIO • GANADORAS TÁCTICAS (9 PM)</b>\n"
                    resumen_texto += f"📅 <i>Fecha: {datetime.now().strftime('%Y-%m-%d')}</i>\n\n"
                    resumen_texto += f"Total de perlas analizadas y mencionadas en el día:\n"
                    resumen_texto += f"<code>{', '.join(monedas_dia)}</code>\n\n"
                    resumen_texto += f"<i>Historial consolidado con éxito. ¡Excelente sesión de trading!</i>"
                    
                    enviar_texto_telegram(resumen_texto)
                    historial["resumen_enviado_hoy"] = True
                    guardar_historial(historial)
                    print("✅ Resumen diario de las 9 PM enviado correctamente.")
