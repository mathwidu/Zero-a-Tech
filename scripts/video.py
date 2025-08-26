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
 'https://www.youtube.com/watch?v=wr868MUcTag',
 'https://www.youtube.com/watch?v=xKRNDalWE-E&list=PLJVvekmbcMxBCh1Cb997PA2hsrxmxdB6G',
 'https://www.youtube.com/watch?v=Pap_Ln-Fz2A&list=PLJVvekmbcMxBCh1Cb997PA2hsrxmxdB6G&index=2',
 'https://www.youtube.com/watch?v=3j5PUUQz5cw&list=PLJVvekmbcMxBCh1Cb997PA2hsrxmxdB6G&index=3',
 'https://www.youtube.com/watch?v=r5utBFtLtWk&list=PLJVvekmbcMxBCh1Cb997PA2hsrxmxdB6G&index=4',
 'https://www.youtube.com/watch?v=oPz7Uh_6ey4&list=PLJVvekmbcMxBCh1Cb997PA2hsrxmxdB6G&index=5',
 'https://www.youtube.com/watch?v=GA8vYmmvqEk&list=PLJVvekmbcMxBCh1Cb997PA2hsrxmxdB6G&index=6',
 'https://www.youtube.com/watch?v=dBE0pZtK3ao&list=PLJVvekmbcMxBCh1Cb997PA2hsrxmxdB6G&index=7',
 'https://www.youtube.com/watch?v=prmMgmdM-xc&list=PLJVvekmbcMxBCh1Cb997PA2hsrxmxdB6G&index=8'
 
]

if __name__ == "__main__":
    for url in videos_para_baixar:
        try:
            print(f"Baixando: {url}")
            baixar_video_youtube(url)
        except Exception as e:
            print(f"Erro ao baixar {url}: {e}")
