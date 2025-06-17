from googleapiclient.discovery import build

API_KEY = "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"  # Google Cloud の API キーを入力

def get_video_info(video_id):
    youtube = build('youtube', 'v3', developerKey=API_KEY)
    request = youtube.videos().list(
        part="snippet",
        id=video_id
    )
    response = request.execute()
    return response

if __name__ == "__main__":
    print(get_video_info("lLtum_qSIuA"))
