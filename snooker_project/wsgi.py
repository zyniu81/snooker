"""
WSGI config for snooker_project project.

It exposes the WSGI callable as a module-level variable named ``application``.

For more information on this file, see
https://docs.djangoproject.com/en/5.0/howto/deployment/wsgi/
"""

import os
import socket
from django.core.wsgi import get_wsgi_application

try:
    _orig_getaddrinfo = socket.getaddrinfo

    def getaddrinfo(*args, **kwargs):
        responses = _orig_getaddrinfo(*args, **kwargs)
        return [r for r in responses if r[0] == socket.AF_INET]

    socket.getaddrinfo = getaddrinfo
except Exception:
    pass

os.environ.setdefault('DJANGO_SETTINGS_MODULE', 'snooker_project.settings')

application = get_wsgi_application()
