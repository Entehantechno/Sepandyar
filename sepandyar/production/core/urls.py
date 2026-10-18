from django.urls import path
from . import views
urlpatterns=[
 path('health',views.health),path('profile',views.profile),path('caregivers',views.caregivers),
 path('medications',views.medications),path('medications/<int:pk>/event',views.medication_event),
 path('vitals',views.vitals),path('alerts',views.alerts),path('alerts/<int:pk>/ack',views.acknowledge_alert)
]
