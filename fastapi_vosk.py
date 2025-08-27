#код должен находится на сервере с поднятым воском
#надо подумать об улучшениях, например разные имена файлов, но у меня маленькая модель (впс 1\1)
#модель работает через задний проход, так что вообще не хочу туда лезть
#сделано чисто чтобы было
#надо посмотреть в сторону бесплатных апи для еонвертации голоса в текст, но пока хз. Я так перевожу голосовухи, нужно адекватное количество токенов, либо локальная модель дома. Но я пк выключаю постоянно. Ситуация

from fastapi import FastAPI, File, UploadFile
from vosk import Model, KaldiRecognizer
import wave
import subprocess
import os
import json

app = FastAPI()

# Загружаем модель один раз
model = Model("model")

@app.post("/stt/")
async def speech_to_text(file: UploadFile = File(...)):
    # Сохраняем временный файл
    input_path = "temp_input.ogg"
    output_path = "temp.wav"

    with open(input_path, "wb") as f:
        f.write(await file.read())

    # Конвертируем в wav 16kHz mono
    subprocess.run(["ffmpeg", "-i", input_path, "-ar", "16000", "-ac", "1", output_path, "-y"],
                   stdout=subprocess.DEVNULL,
                   stderr=subprocess.DEVNULL)

    # Распознаём
    wf = wave.open(output_path, "rb")
    rec = KaldiRecognizer(model, wf.getframerate())
    rec.SetWords(True)

    result_text = ""
    while True:
        data = wf.readframes(4000)
        if len(data) == 0:
            break
        if rec.AcceptWaveform(data):
            result_text += json.loads(rec.Result())["text"] + " "
    result_text += json.loads(rec.FinalResult())["text"]

    # Чистим временные файлы
    os.remove(input_path)
    os.remove(output_path)

    return {"text": result_text.strip()}
