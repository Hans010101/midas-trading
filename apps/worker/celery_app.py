from celery import Celery

app = Celery("midas-worker")
app.config_from_object("config.celery_config")
app.autodiscover_tasks(["tasks"])
