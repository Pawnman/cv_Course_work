from ultralytics import YOLO

# Загрузка моделей YOLO
detection_model = YOLO("yolov8n.pt")  # Модель для детекции
segmentation_model = YOLO("yolov8n-seg.pt")  # Модель для сегментации
tracking_model = YOLO("yolov8n-seg.pt")  # Модель для трекинга (можно использовать ту же, что и для сегментации)
