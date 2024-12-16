import os
import uuid
import shutil
import cv2

from fastapi import FastAPI, File, UploadFile, HTTPException
from fastapi.responses import JSONResponse, FileResponse

from models import detection_model, segmentation_model, tracking_model

app = FastAPI()

# Папки для хранения файлов
UPLOAD_DIR = "uploads"
RESULT_DIR = "results"
os.makedirs(UPLOAD_DIR, exist_ok=True)
os.makedirs(RESULT_DIR, exist_ok=True)

# Хранение задач
tasks = {}

# Идентификаторы классов, которые нужно детектировать
ALLOWED_CLASS_IDS = [4, 8]  # 4 - airplane, 8 - boat

@app.post("/upload_image_detection")
async def upload_image(file: UploadFile = File(...)):
    return await process_file(file, "detection", "image")


@app.post("/upload_image_segmentation")
async def upload_image(file: UploadFile = File(...)):
    return await process_file(file, "segmentation", "image")


@app.post("/upload_video")
async def upload_video(file: UploadFile = File(...)):
    return await process_file(file, "tracking", "video")

async def process_file(file: UploadFile, task_type: str, file_type: str):
    task_id = str(uuid.uuid4())
    file_path = os.path.join(UPLOAD_DIR, f"{task_id}.{file.filename.split('.')[-1]}")
    
    with open(file_path, "wb") as buffer:
        shutil.copyfileobj(file.file, buffer)
    
    tasks[task_id] = {"status": "pending", "type": task_type, "file_type": file_type}
    process_file_task(task_id, file_path, task_type, file_type)
    return JSONResponse({"task_id": task_id})

def filter_results(results):
    """
    Фильтрует результаты YOLO, оставляя только объекты разрешенных классов.
    """
    results[0].boxes.data = [det for det in results[0].boxes.data if int(det[5]) in ALLOWED_CLASS_IDS]
    return results


def process_file_task(task_id, file_path, task_type, file_type):
    try:
        model = {
            "detection": detection_model,
            "segmentation": segmentation_model,
            "tracking": tracking_model,
        }.get(task_type)
        
        if not model:
            raise ValueError("Unsupported task type")
        
        if file_type == "video":
            cap = cv2.VideoCapture(file_path)
            frame_width = int(cap.get(cv2.CAP_PROP_FRAME_WIDTH))
            frame_height = int(cap.get(cv2.CAP_PROP_FRAME_HEIGHT))
            fps = int(cap.get(cv2.CAP_PROP_FPS))
            result_path = os.path.join(RESULT_DIR, f"{task_id}.mp4")
            out = cv2.VideoWriter(result_path, cv2.VideoWriter_fourcc(*'mp4v'), fps, (frame_width, frame_height))
            
            while cap.isOpened():
                ret, frame = cap.read()
                if not ret:
                    break
                
                # Обработка кадра с помощью YOLO
                if task_type == "tracking":
                    # Для трекинга передаем список разрешенных классов
                    results = model.track(frame, persist=True, classes=ALLOWED_CLASS_IDS) # ТУТ КЛАССЫ ПРОПИСАЛ
                else:
                    # Для детекции и сегментации фильтруем результаты
                    results = model(frame)
                    results = filter_results(results)
                
                # Получение аннотированного кадра
                annotated_frame = results[0].plot()
                
                # Запись кадра в видео
                out.write(annotated_frame)
            
            cap.release()
            out.release()
        else:
            # Обработка изображения
            results = model.predict(source=file_path, classes=ALLOWED_CLASS_IDS)
            result_path = os.path.join(RESULT_DIR, f"{task_id}.jpg")
            results[0].save(result_path)
        
        tasks[task_id]["status"] = "done"
        tasks[task_id]["result_url"] = f"/result/{task_id}"
    except Exception as e:
        tasks[task_id]["status"] = "error"
        tasks[task_id]["message"] = str(e)

@app.get("/status/{task_id}")
async def get_status(task_id: str):
    if task_id not in tasks:
        raise HTTPException(status_code=404, detail="Task not found")
    return JSONResponse(tasks[task_id])

@app.get("/result/{task_id}")
async def get_result(task_id: str):
    if task_id not in tasks:
        raise HTTPException(status_code=404, detail="Task not found")
    if tasks[task_id]["status"] != "done":
        raise HTTPException(status_code=400, detail="Result not ready")
    
    file_type = tasks[task_id]["file_type"]
    result_file = f"{task_id}.mp4" if file_type == "video" else f"{task_id}.jpg"
    result_path = os.path.join(RESULT_DIR, result_file)
    if not os.path.exists(result_path):
        raise HTTPException(status_code=404, detail="Result file not found")
    
    return JSONResponse({"result_url": f"/download/{task_id}"})

@app.get("/download/{task_id}")
async def download_result(task_id: str):
    file_type = tasks[task_id]["file_type"]
    result_file = f"{task_id}.mp4" if file_type == "video" else f"{task_id}.jpg"
    result_path = os.path.join(RESULT_DIR, result_file)
    if not os.path.exists(result_path):
        raise HTTPException(status_code=404, detail="Result file not found")
    
    media_type = "video/mp4" if file_type == "video" else "image/jpeg"
    return FileResponse(result_path, media_type=media_type, filename=f"result_{task_id}.{file_type}")
