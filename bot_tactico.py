name: Etapa 1 - Cazador Tactico
on:
  workflow_dispatch:

permissions:
  contents: write

jobs:
  run-tactico:
    runs-on: ubuntu-latest
    steps:
      - uses: actions/checkout@v4
      - uses: actions/setup-python@v5
        with:
          python-version: '3.11'
      - name: Instalar dependencias
        run: pip install requests matplotlib google-genai
      - name: Ejecutar Cazador Tactico
        env:
          TELEGRAM_BOT_TOKEN: ${{ secrets.TELEGRAM_BOT_TOKEN }}
          TELEGRAM_CHAT_ID: ${{ secrets.TELEGRAM_CHAT_ID }}
          TOPIC_ID_TACTICO: ${{ secrets.TOPIC_ID_TACTICO }}
          GEMINI_API_KEY: ${{ secrets.GEMINI_API_KEY }}
        run: python bot_tactico.py
      - name: Guardar historial actualizado
        run: |
          git config user.name "github-actions[bot]"
          git config user.email "github-actions[bot]@users.noreply.github.com"
          git add historial_perlas.json historial_ganadoras.json
          git diff --staged --quiet || git commit -m "Update historial desde Cazador Tactico"
          git push
