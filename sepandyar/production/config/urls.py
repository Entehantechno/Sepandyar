from django.urls import path, include
from core import auth_views
urlpatterns=[path('api/',include('core.urls')),path('api/auth/register',auth_views.register),path('api/auth/login',auth_views.login),path('api/auth/me',auth_views.me)]
