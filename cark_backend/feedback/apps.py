from django.apps import AppConfig


class FeedbackConfig(AppConfig):
    default_auto_field = 'django.db.models.BigAutoField'  # type: ignore
    name = 'feedback'
    
    def ready(self):
        import feedback.signals
