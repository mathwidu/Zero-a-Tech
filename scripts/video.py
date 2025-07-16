import yt_dlp
import os

def baixar_video_youtube(url, destino='assets/videos_fundo'):
    os.makedirs(destino, exist_ok=True)
    ydl_opts = {
        'outtmpl': f'{destino}/%(title).40s.%(ext)s',
        'format': 'bestvideo[ext=mp4]+bestaudio[ext=m4a]/mp4',
        'merge_output_format': 'mp4',
        'quiet': False,
        'noplaylist': True
    }

    with yt_dlp.YoutubeDL(ydl_opts) as ydl:
        ydl.download([url])

# Lista de vídeos recomendados (exemplo: satisfatórios / gameplays CC)
videos_para_baixar = [
 'https://www.youtube.com/watch?v=cWDpLJkXtlQ'
]

if __name__ == "__main__":
    for url in videos_para_baixar:
        try:
            print(f"Baixando: {url}")
            baixar_video_youtube(url)
        except Exception as e:
            print(f"Erro ao baixar {url}: {e}")
