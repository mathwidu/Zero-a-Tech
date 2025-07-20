from selenium import webdriver
from selenium.webdriver.chrome.options import Options
from selenium.webdriver.common.by import By
from selenium.webdriver.support.ui import WebDriverWait
from selenium.webdriver.support import expected_conditions as EC
from selenium.webdriver.common.keys import Keys
from selenium.common.exceptions import ElementNotInteractableException
import os, time, re

def remover_emojis(texto):
    return re.sub(r'[^\u0000-\uFFFF]', '', texto)

def limpar_legenda(texto):
    texto = texto.strip()
    texto = re.sub(r'^[vV]\s*', '', texto)  # remove 'v ' ou 'V' no início
    texto = texto.replace("＃", "#").replace("﹟", "#")  # normaliza #
    texto = remover_emojis(texto)
    return texto

def postar_no_tiktok():
    VIDEO_PATH = os.path.abspath("output/video_final.mp4")
    CAPTION_PATH = os.path.abspath("output/legenda_tiktok.txt")

    with open(CAPTION_PATH, "r", encoding="utf-8") as f:
        legenda = limpar_legenda(f.read())

    options = Options()
    options.debugger_address = "127.0.0.1:9222"
    driver = webdriver.Chrome(options=options)

    try:
        print("🌐 Acessando TikTok Upload...")
        driver.get("https://www.tiktok.com/upload")

        print("⏳ Aguardando campo de upload...")
        input_upload = WebDriverWait(driver, 30).until(
            EC.presence_of_element_located((By.XPATH, '//input[@type="file"]'))
        )

        print("📤 Enviando vídeo...")
        input_upload.send_keys(VIDEO_PATH)

        print("⏳ Aguardando confirmação de 'Enviado'...")
        WebDriverWait(driver, 120).until(
            EC.presence_of_element_located((By.XPATH, '//*[contains(text(), "Enviado")]'))
        )

        print("⏳ Localizando campo editável de legenda...")
        editable_div = WebDriverWait(driver, 60).until(
            EC.element_to_be_clickable((By.XPATH, '//div[@contenteditable="true"]'))
        )

        print("🧹 Limpando legenda anterior...")
        editable_div.click()
        editable_div.send_keys(Keys.COMMAND + "a")
        editable_div.send_keys(Keys.DELETE)
        time.sleep(1)

        print("📝 Escrevendo nova legenda...")
        for palavra in legenda.split():
            editable_div.send_keys(palavra)
            if palavra.startswith("#"):
                editable_div.send_keys(" ")
            else:
                editable_div.send_keys(" ")
            time.sleep(0.05)

        time.sleep(2)

        print("🚀 Localizando botão 'Publicar'...")
        botao_postar = WebDriverWait(driver, 60).until(
            EC.element_to_be_clickable((By.XPATH, '//button[.//div[text()="Publicar"]]'))
        )

        print("✅ Clicando no botão...")
        botao_postar.click()

        print("🎉 Vídeo publicado com legenda correta!")

    except ElementNotInteractableException:
        print("⚠️ Não foi possível interagir com o campo de legenda.")
    except Exception as e:
        print(f"❌ Erro: {e}")
    finally:
        time.sleep(10)
        driver.quit()
if __name__ == "__main__":
    postar_no_tiktok()
