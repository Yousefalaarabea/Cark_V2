from django.apps import AppConfig


class SelfdriveRentalsConfig(AppConfig):
    default_auto_field = 'django.db.models.BigAutoField'
    name = 'selfdrive_rentals'
    
    def ready(self):
        """Import signals when app is ready"""
        import selfdrive_rentals.signals