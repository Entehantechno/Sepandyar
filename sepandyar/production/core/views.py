from django.utils import timezone
from rest_framework.decorators import api_view
from rest_framework.response import Response
from rest_framework import status
from .models import Profile,Caregiver,Medication,Vital,Alert
from .serializers import *
@api_view(['GET'])
def health(request): return Response({'ok':True,'service':'sepandyar-django','time':timezone.now()})
@api_view(['GET','POST'])
def profile(request):
 obj=Profile.objects.first()
 if request.method=='GET': return Response(ProfileSerializer(obj).data if obj else {})
 if obj: ser=ProfileSerializer(obj,data=request.data,partial=True)
 else: ser=ProfileSerializer(data=request.data)
 ser.is_valid(raise_exception=True); obj=ser.save(); return Response(ProfileSerializer(obj).data,status=200)
@api_view(['GET','POST'])
def caregivers(request):
 if request.method=='GET': return Response({'items':CaregiverSerializer(Caregiver.objects.all(),many=True).data})
 ser=CaregiverSerializer(data=request.data); ser.is_valid(raise_exception=True); obj=ser.save(); return Response(CaregiverSerializer(obj).data,status=201)
@api_view(['GET','POST'])
def medications(request):
 if request.method=='GET': return Response({'items':MedicationSerializer(Medication.objects.order_by('time'),many=True).data})
 ser=MedicationSerializer(data=request.data); ser.is_valid(raise_exception=True); return Response(MedicationSerializer(ser.save()).data,status=201)
@api_view(['POST'])
def medication_event(request,pk):
 try: obj=Medication.objects.get(pk=pk)
 except Medication.DoesNotExist:return Response({'error':'not_found'},status=404)
 obj.status=request.data.get('event','pending'); obj.save(update_fields=['status']); return Response({'ok':True,'status':obj.status})
@api_view(['GET','POST'])
def vitals(request):
 if request.method=='GET': return Response({'items':VitalSerializer(Vital.objects.order_by('-measured_at')[:100],many=True).data})
 ser=VitalSerializer(data=request.data); ser.is_valid(raise_exception=True); return Response(VitalSerializer(ser.save()).data,status=201)
@api_view(['GET'])
def alerts(request): return Response({'items':AlertSerializer(Alert.objects.filter(status='open').order_by('-created_at')[:50],many=True).data})
@api_view(['POST'])
def acknowledge_alert(request,pk):
 updated=Alert.objects.filter(pk=pk).update(status='acknowledged'); return Response({'ok':bool(updated)})
