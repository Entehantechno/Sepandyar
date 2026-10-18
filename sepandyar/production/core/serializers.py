from rest_framework import serializers
from .models import Profile,Caregiver,Medication,Vital,Alert
class ProfileSerializer(serializers.ModelSerializer):
 class Meta: model=Profile; fields='__all__'
class CaregiverSerializer(serializers.ModelSerializer):
 class Meta: model=Caregiver; fields='__all__'
class MedicationSerializer(serializers.ModelSerializer):
 class Meta: model=Medication; fields='__all__'
class VitalSerializer(serializers.ModelSerializer):
 class Meta: model=Vital; fields='__all__'
class AlertSerializer(serializers.ModelSerializer):
 class Meta: model=Alert; fields='__all__'
