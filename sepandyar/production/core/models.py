from django.db import models
class Profile(models.Model):
    name=models.CharField(max_length=120)
    age=models.PositiveIntegerField(null=True,blank=True)
    needs=models.TextField(blank=True)
    assistant_name=models.CharField(max_length=80,default='سپندیار')
    updated_at=models.DateTimeField(auto_now=True)
class Caregiver(models.Model):
    name=models.CharField(max_length=120)
    phone=models.CharField(max_length=30)
    role=models.CharField(max_length=30,default='family')
    permissions=models.JSONField(default=list)
    created_at=models.DateTimeField(auto_now_add=True)
class Medication(models.Model):
    name=models.CharField(max_length=160)
    time=models.TimeField()
    instructions=models.CharField(max_length=255,blank=True)
    status=models.CharField(max_length=20,default='pending')
class Vital(models.Model):
    type=models.CharField(max_length=40)
    value=models.JSONField()
    source=models.CharField(max_length=30,default='manual')
    measured_at=models.DateTimeField()
    created_at=models.DateTimeField(auto_now_add=True)
class Alert(models.Model):
    type=models.CharField(max_length=60)
    message=models.TextField()
    severity=models.CharField(max_length=20,default='normal')
    status=models.CharField(max_length=20,default='open')
    created_at=models.DateTimeField(auto_now_add=True)
