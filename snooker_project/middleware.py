from django.shortcuts import render
from django.conf import settings
from django.urls import reverse

class MaintenanceModeMiddleware:
    def __init__(self, get_response):
        self.get_response = get_response

    def __call__(self, request):
        # Check if maintenance mode is enabled (default False)
        maintenance_mode = getattr(settings, 'MAINTENANCE_MODE', False)

        if maintenance_mode:
            # 1. We allow access to the Admin Panel (/admin/)
            #2. We allow static files (CSS/JS) to make the 503 page look nice
            path = request.path
            if path.startswith('/admin/') or path.startswith('/static/') or path.startswith('/media/'):
                return self.get_response(request)

            # For everyone else -> Show maintenance page
            context = {
                'message': getattr(settings, 'MAINTENANCE_MSG', '')
            }
            return render(request, '503.html', context, status=503)

        return self.get_response(request)